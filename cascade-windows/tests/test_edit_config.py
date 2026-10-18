import unittest

from cascade_windows.cli import editor_command

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


if __name__ == "__main__":
    unittest.main()
