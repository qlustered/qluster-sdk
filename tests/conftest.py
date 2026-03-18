import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),
                                             'tests')))


current_dir = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(current_dir, 'fixtures/')
