"""Long jobs hold off idle sleep, and only while they run (no real caffeinate is started)."""
from __future__ import annotations

import unittest
from unittest import mock

from vidforge import awake


class Hold(unittest.TestCase):
    def test_mac_holds_once_for_nested_jobs_and_lets_go_after(self):
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("shutil.which", return_value="/usr/bin/caffeinate"), \
                mock.patch("subprocess.Popen") as popen, mock.patch.dict("os.environ", {"VIDFORGE_KEEP_AWAKE": "1"}):
            with awake.hold():
                with awake.hold():          # the UI's watcher around pipeline.build()'s own
                    pass
                popen.return_value.terminate.assert_not_called()
            self.assertEqual(popen.call_count, 1)
            self.assertIn("-i", popen.call_args[0][0])
            popen.return_value.terminate.assert_called_once()

    def test_can_be_switched_off_and_never_fails_the_job(self):
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("shutil.which", return_value="/usr/bin/caffeinate"), \
                mock.patch("subprocess.Popen", side_effect=OSError("no")) as popen:
            with mock.patch.dict("os.environ", {"VIDFORGE_KEEP_AWAKE": "0"}):
                with awake.hold():
                    pass
            popen.assert_not_called()
            with mock.patch.dict("os.environ", {"VIDFORGE_KEEP_AWAKE": "1"}):
                with awake.hold():          # caffeinate missing or refusing is not the job's problem
                    ran = True
            self.assertTrue(ran)

    def test_the_job_s_own_error_still_comes_out_and_the_hold_is_released(self):
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("shutil.which", return_value="/usr/bin/caffeinate"), \
                mock.patch("subprocess.Popen") as popen, mock.patch.dict("os.environ", {"VIDFORGE_KEEP_AWAKE": "1"}):
            with self.assertRaises(ValueError):
                with awake.hold():
                    raise ValueError("render failed")
            popen.return_value.terminate.assert_called_once()
            self.assertEqual(getattr(awake._local, "depth", 0), 0)


if __name__ == "__main__":
    unittest.main()
