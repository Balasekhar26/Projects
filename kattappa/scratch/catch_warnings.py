import glob
import py_compile
import warnings

warnings.simplefilter('error', SyntaxWarning)

for f in glob.glob('backend/**/*.py', recursive=True):
    try:
        py_compile.compile(f)
    except Exception as e:
        print(f"Error/Warning in {f}: {e}")
