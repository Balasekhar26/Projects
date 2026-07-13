import glob
import re

files = glob.glob('backend/**/*.py', recursive=True)
count = 0

for filepath in files:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Prepend raw string marker to triple quoted docstrings containing \P or similar
    pattern = re.compile(r'"""(.*?)"""', re.DOTALL)
    
    def replacer(match):
        inner = match.group(1)
        if "\\" in inner:
            return 'r"""' + inner + '"""'
        return '"""' + inner + '"""'

    new_content = pattern.sub(replacer, content)
    
    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Refactored: {filepath}")
        count += 1

print(f"SyntaxWarnings refactoring completed. Modified {count} files.")
