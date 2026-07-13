import glob
import py_compile
import warnings

warnings.simplefilter('error', SyntaxWarning)

for f in glob.glob('backend/**/*.py', recursive=True):
    try:
        py_compile.compile(f, doraise=True)
    except Exception as e:
        print(f"File: {f}")
        print(f"Exception class: {e.__class__}")
        print(f"Message: {e}")
        if hasattr(e, 'lineno'):
            print(f"Line: {e.lineno}")
        if hasattr(e, 'text'):
            print(f"Text: {repr(e.text)}")
        if hasattr(e, 'filename'):
            print(f"Filename: {e.filename}")
        print("-" * 40)
