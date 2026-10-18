import unittest

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


if __name__ == "__main__":
    unittest.main()
