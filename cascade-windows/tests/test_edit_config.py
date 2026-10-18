import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from cascade_windows import cli
from cascade_windows.settings import (
    Settings, SettingsError, configured_editor, default_settings_dict, settings_from_dict, settings_to_dict,
)

from cascade_windows.cli import chosen_editor_command, editor_command, run_chosen_editor

PATH = "/home/user/.config/cascade-windows/config.json"


def tools(*names):
    return lambda name: "/usr/bin/" + name if name in names else None


class EditorCommandTest(unittest.TestCase):
    def test_the_default_text_editor_is_used_instead_of_the_json_handler(self):
        command = editor_command(PATH, tools("xdg-mime", "gtk-launch", "xdg-open"), lambda mime: "xed.desktop\n")
        self.assertEqual(command, ["gtk-launch", "xed.desktop", PATH])

    def test_the_query_asks_for_plain_text(self):
        asked = []
        editor_command(PATH, tools("xdg-mime", "gtk-launch"), lambda mime: asked.append(mime) or "xed.desktop")
        self.assertEqual(asked, ["text/plain"])

    def test_xdg_open_is_the_fallback_when_there_is_no_text_editor_entry(self):
        command = editor_command(PATH, tools("xdg-mime", "gtk-launch", "xdg-open"), lambda mime: "")
        self.assertEqual(command, ["/usr/bin/xdg-open", PATH])

    def test_xdg_open_is_the_fallback_without_gtk_launch(self):
        command = editor_command(PATH, tools("xdg-mime", "xdg-open"), lambda mime: "xed.desktop")
        self.assertEqual(command, ["/usr/bin/xdg-open", PATH])

    def test_nothing_is_started_when_no_tool_exists(self):
        self.assertIsNone(editor_command(PATH, tools(), lambda mime: ""))


class ChosenEditorTest(unittest.TestCase):
    def test_the_file_follows_the_editor_and_its_arguments(self):
        command = chosen_editor_command("code --wait", PATH, tools("code"))
        self.assertEqual(command, ["code", "--wait", PATH])

    def test_quoted_arguments_stay_together(self):
        command = chosen_editor_command("my-editor --title 'a b'", PATH, tools("my-editor"))
        self.assertEqual(command, ["my-editor", "--title", "a b", PATH])

    def test_an_editor_that_does_not_exist_is_reported(self):
        with self.assertRaises(ValueError) as context:
            chosen_editor_command("no-such-editor", PATH, tools("gedit"))
        self.assertIn("no-such-editor", str(context.exception))

    def test_an_empty_or_broken_value_is_reported(self):
        for value in ("", "   ", "gedit 'unclosed"):
            with self.assertRaises(ValueError):
                chosen_editor_command(value, PATH, tools("gedit"))

    def test_the_command_runs_and_its_exit_code_is_returned(self):
        self.assertEqual(run_chosen_editor("true", PATH), 0)
        self.assertEqual(run_chosen_editor("false", PATH), 1)
        self.assertEqual(run_chosen_editor("no-such-editor-xyz", PATH), 1)


class EditorSettingTest(unittest.TestCase):
    def test_the_default_is_no_editor_and_it_is_written_to_the_default_file(self):
        self.assertEqual(Settings().editor, "")
        self.assertEqual(default_settings_dict()["editor"], "")

    def test_the_value_is_read_trimmed_and_written_back(self):
        settings = settings_from_dict({"editor": "  code --wait "})
        self.assertEqual(settings.editor, "code --wait")
        self.assertEqual(settings_to_dict(settings)["editor"], "code --wait")

    def test_it_must_be_text(self):
        for value in (3, True, ["gedit"], None):
            with self.assertRaises(SettingsError):
                settings_from_dict({"editor": value})

    def write(self, text):
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, True))
        path = os.path.join(folder, "config.json")
        with open(path, "w") as handle:
            handle.write(text)
        return path

    def test_configured_editor_reads_the_file(self):
        self.assertEqual(configured_editor(self.write('{"editor": "xed"}')), "xed")
        self.assertEqual(configured_editor(self.write("{}")), "")
        self.assertEqual(configured_editor(os.path.join(tempfile.gettempdir(), "no-such-cascade-config.json")), "")

    def test_configured_editor_still_works_when_other_settings_are_broken(self):
        # --edit-config is how a broken file gets fixed, so one bad value must not hide the editor.
        self.assertEqual(configured_editor(self.write('{"editor": "nano", "margin": {"top": -5}}')), "nano")
        self.assertEqual(configured_editor(self.write("{ not json")), "")

    def run_edit(self, config_text, *args):
        path = self.write(config_text)
        with mock.patch.object(cli, "run_chosen_editor", return_value=0) as chosen, \
                mock.patch.object(cli.subprocess, "Popen") as popen, \
                mock.patch.object(cli, "editor_command", return_value=["default-editor", path]), \
                contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["--config", path, "--edit-config"] + list(args))
        return code, chosen, popen, path

    def test_the_setting_chooses_the_editor(self):
        code, chosen, popen, path = self.run_edit('{"editor": "xed"}')
        self.assertEqual(code, 0)
        chosen.assert_called_once_with("xed", path)
        popen.assert_not_called()

    def test_the_command_line_option_wins_over_the_setting(self):
        _code, chosen, _popen, path = self.run_edit('{"editor": "xed"}', "--editor", "nano")
        chosen.assert_called_once_with("nano", path)

    def test_without_either_the_default_text_editor_is_used(self):
        _code, chosen, popen, path = self.run_edit("{}")
        chosen.assert_not_called()
        popen.assert_called_once_with(["default-editor", path])


class NotifyExcludedSettingTest(unittest.TestCase):
    def test_the_default_is_on_inside_the_notify_section(self):
        self.assertTrue(Settings().notify_excluded)
        self.assertEqual(default_settings_dict()["notify"], {"excluded": True})
        self.assertNotIn("excluded_notification", default_settings_dict())

    def test_it_must_be_true_or_false(self):
        with self.assertRaises(SettingsError):
            settings_from_dict({"notify": {"excluded": "no"}})

    def test_the_short_lived_name_still_works_and_is_reported(self):
        warnings = []
        settings = settings_from_dict({"excluded_notification": False}, warnings.append)
        self.assertFalse(settings.notify_excluded)
        self.assertEqual(len(warnings), 1)
        self.assertIn("notify.excluded", warnings[0])

    def test_the_current_name_wins_over_the_short_lived_one(self):
        settings = settings_from_dict(
            {"notify": {"excluded": True}, "excluded_notification": False}, lambda message: None)
        self.assertTrue(settings.notify_excluded)

    def test_the_written_default_file_explains_the_setting(self):
        from cascade_windows.settings import documented_default_dict

        documented = documented_default_dict()
        self.assertIn("notification", documented["notify"]["comment"])
        self.assertIn("comment_editor", documented)
        self.assertNotIn("excluded_notification", documented)
        self.assertNotIn("comment_excluded_notification", documented)

    def test_an_untouched_old_default_file_is_still_removed_and_a_changed_one_kept(self):
        from cascade_windows.settings import remove_legacy_default_config

        def old_file(notify):
            data = default_settings_dict()
            data["margin"] = {"top": 20, "right": 20, "bottom": 20, "left": 20}
            data["step"] = {"x": 30, "y": 30}
            del data["skip"]["dialogs"]
            del data["editor"]
            data["notify"] = notify
            return data

        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, True))
        path = os.path.join(folder, "config.json")
        for notify, removed in (({"excluded": True}, True), ({"excluded": False}, False)):
            with open(path, "w") as handle:
                json.dump(old_file(notify), handle)
            self.assertEqual(remove_legacy_default_config(path), removed)
            self.assertEqual(os.path.exists(path), not removed)


if __name__ == "__main__":
    unittest.main()
