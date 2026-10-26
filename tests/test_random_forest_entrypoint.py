import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

class EntrypointTest(unittest.TestCase):
    def test_selects_only_requested_family(self):
        with patch('scripts.evaluate_regression_suite.run') as run:
            with patch.object(sys, 'argv', ['runner','--input-dir','inputs','--ridge-dir','ridge','--output','new-output']):
                runpy.run_module('scripts.evaluate_random_forest', run_name='__main__')
            run.assert_called_once_with(Path('inputs'),Path('ridge'),Path('new-output'),models=['random_forest'])

if __name__=='__main__':unittest.main()
