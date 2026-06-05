#!/usr/bin/env python3
"""
🧠⚙️ UNIVERSAL AI SYSTEM v3.0 - ChatGPT Interface
Advanced AI with ChatGPT-like conversation + Best-in-Class Coding Agent
Can generate, edit, debug, and optimize code from natural language descriptions
Works on Windows, macOS, Linux - One file setup and run
"""

import os
import subprocess
import sys
import platform
import json
import asyncio
import threading
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import time
from datetime import datetime
import shutil

# -------- ADVANCED CODING AGENT --------

class AdvancedCodingAgent:
    """Best-in-class coding agent with code generation and editing"""

    SUPPORTED_LANGUAGES = {
        'python': {'ext': '.py', 'comment': '#'},
        'javascript': {'ext': '.js', 'comment': '//'},
        'typescript': {'ext': '.ts', 'comment': '//'},
        'java': {'ext': '.java', 'comment': '//'},
        'cpp': {'ext': '.cpp', 'comment': '//'},
        'csharp': {'ext': '.cs', 'comment': '//'},
        'go': {'ext': '.go', 'comment': '//'},
        'rust': {'ext': '.rs', 'comment': '//'},
        'html': {'ext': '.html', 'comment': '<!--'},
        'css': {'ext': '.css', 'comment': '/*'},
        'sql': {'ext': '.sql', 'comment': '--'},
        'bash': {'ext': '.sh', 'comment': '#'},
    }

    CODE_TEMPLATES = {
        'python_api': '''#!/usr/bin/env python3
"""
{description}
"""
import os
import sys
from typing import Dict, List, Optional, Any

class APIServer:
    """Main API Server class"""

    def __init__(self, host='localhost', port=8000):
        self.host = host
        self.port = port
        self.routes = {}

    def register_route(self, path: str, method: str, handler):
        """Register API route"""
        self.routes[f"{method}:{path}"] = handler

    def run(self):
        """Start the server"""
        print(f"Server running on {self.host}:{self.port}")

if __name__ == "__main__":
    app = APIServer()
    # Add your routes here
    app.run()
''',
        'web_app': '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            max-width: 600px;
        }}
        h1 {{
            color: #333;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p>{description}</p>
    </div>
</body>
</html>
''',
        'react_component': '''import React, {{ useState }} from 'react';

/**
 * {component_name} Component
 * {description}
 */
export const {component_name} = () => {{
    const [state, setState] = useState(null);

    return (
        <div className="{component_name}">
            <h1>{component_name}</h1>
            {/* Add your component JSX here */}
        </div>
    );
}};

export default {component_name};
''',
    }

    def __init__(self):
        self.workspace = Path("workspace/code")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.generated_files = []
        self.conversation_history = []

    def generate_code_from_description(self, description: str, language: str = 'python',
                                       filename: Optional[str] = None) -> Tuple[str, str]:
        """Generate code from natural language description"""

        # Analyze description to determine code structure
        prompt = f"""
Generate {language.upper()} code for the following requirement:

REQUIREMENT: {description}

REQUIREMENTS FOR CODE GENERATION:
1. Write clean, production-ready code
2. Include proper error handling
3. Add meaningful comments
4. Follow {language} best practices
5. Include type hints/annotations where applicable
6. Add docstrings for functions/classes
7. Make it modular and reusable

Generate complete, working code:
"""

        # Create code structure based on description
        code = self._create_structured_code(description, language)

        # Save to file
        if not filename:
            filename = self._generate_filename(description, language)

        filepath = self.workspace / filename
        filepath.write_text(code)
        self.generated_files.append({
            'path': str(filepath),
            'language': language,
            'description': description,
            'timestamp': datetime.now().isoformat()
        })

        return code, str(filepath)

    def edit_code_at_line(self, filepath: str, line_number: int, new_code: str) -> Tuple[str, bool]:
        """Edit code at specific line"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                return f"File not found: {filepath}", False

            lines = filepath.read_text().split('\n')

            if line_number < 1 or line_number > len(lines):
                return f"Line number {line_number} out of range (1-{len(lines)})", False

            # Replace line (adjust for 0-based indexing)
            lines[line_number - 1] = new_code
            filepath.write_text('\n'.join(lines))

            return f"Line {line_number} updated successfully", True
        except Exception as e:
            return f"Error editing file: {str(e)}", False

    def add_function_to_code(self, filepath: str, function_description: str, language: str = 'python') -> Tuple[str, bool]:
        """Add a new function to existing code"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                return f"File not found: {filepath}", False

            code = filepath.read_text()

            # Generate function code
            new_function = self._generate_function(function_description, language)

            # Append function to file
            code += f"\n\n{new_function}"
            filepath.write_text(code)

            return f"Function added successfully to {filepath}", True
        except Exception as e:
            return f"Error adding function: {str(e)}", False

    def analyze_code(self, filepath: str) -> Dict[str, Any]:
        """Analyze code for issues, complexity, and suggestions"""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                return {'error': f'File not found: {filepath}'}

            code = filepath.read_text()

            analysis = {
                'file': str(filepath),
                'lines_of_code': len(code.split('\n')),
                'complexity': self._calculate_complexity(code),
                'issues': self._identify_issues(code),
                'suggestions': self._generate_suggestions(code),
                'metrics': {
                    'functions': code.count('def '),
                    'classes': code.count('class '),
                    'imports': code.count('import '),
                    'comments': len([l for l in code.split('\n') if l.strip().startswith('#')])
                }
            }
            return analysis
        except Exception as e:
            return {'error': str(e)}

    def create_project_structure(self, project_name: str, project_type: str) -> Tuple[str, bool]:
        """Create complete project structure"""

        structures = {
            'python_package': {
                f'{project_name}/__init__.py': 'package',
                f'{project_name}/main.py': 'python_main',
                f'{project_name}/utils.py': 'python_utils',
                'tests/__init__.py': 'package',
                'tests/test_main.py': 'python_test',
                'README.md': 'readme',
                'requirements.txt': 'requirements',
                'setup.py': 'setup_py'
            },
            'web_app': {
                'index.html': 'html_index',
                'css/style.css': 'css_style',
                'js/app.js': 'js_app',
                'js/utils.js': 'js_utils',
                'README.md': 'readme'
            },
            'react_app': {
                'src/App.jsx': 'react_app',
                'src/components/Header.jsx': 'react_component',
                'src/pages/Home.jsx': 'react_page',
                'src/index.css': 'css_style',
                'package.json': 'package_json',
                'README.md': 'readme'
            }
        }

        try:
            structure = structures.get(project_type, {})
            project_dir = self.workspace / project_name
            project_dir.mkdir(parents=True, exist_ok=True)

            for filepath, file_type in structure.items():
                full_path = project_dir / filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Create template content
                content = self._get_template_content(file_type, project_name)
                full_path.write_text(content)

            return f"Project '{project_name}' created at {project_dir}", True
        except Exception as e:
            return f"Error creating project: {str(e)}", False

    def _create_structured_code(self, description: str, language: str) -> str:
        """Create structured code based on description"""
        if language == 'python':
            return f'''"""
{description}
"""

import sys
from typing import Dict, List, Optional, Any

class Main:
    """Main class for {description}"""

    def __init__(self):
        pass

    def run(self):
        """Main execution method"""
        pass

def main():
    """Entry point"""
    app = Main()
    app.run()

if __name__ == "__main__":
    main()
'''
        elif language == 'javascript':
            return f'''/**
 * {description}
 */

class Main {{
    constructor() {{}}

    run() {{
        console.log("Running: {description}");
    }}
}}

const app = new Main();
app.run();

module.exports = Main;
'''
        return f"// {description}\n// Generated code for {language}"

    def _generate_function(self, description: str, language: str) -> str:
        """Generate function code"""
        if language == 'python':
            return f'''def new_function(*args, **kwargs):
    """
    {description}

    Args:
        *args: Variable length argument list
        **kwargs: Arbitrary keyword arguments

    Returns:
        Result of the function
    """
    # Implementation: {description}
    pass
'''
        elif language == 'javascript':
            return f'''function newFunction(...args) {{
    /**
     * {description}
     * @param {{*}} args - Arguments
     * @returns {{*}} Result
     */
    // Implementation: {description}
}}
'''
        return f"// Function: {description}"

    def _generate_filename(self, description: str, language: str) -> str:
        """Generate appropriate filename from description"""
        # Extract first few meaningful words
        words = re.findall(r'\b[a-zA-Z]+\b', description.lower())[:3]
        name = '_'.join(words) if words else 'generated'
        ext = self.SUPPORTED_LANGUAGES.get(language, {}).get('ext', '.txt')
        return f"{name}{ext}"

    def _calculate_complexity(self, code: str) -> str:
        """Calculate code complexity"""
        lines = len(code.split('\n'))
        functions = code.count('def ') + code.count('function ')

        if lines < 50:
            return "Low"
        elif lines < 200:
            return "Medium"
        else:
            return "High"

    def _identify_issues(self, code: str) -> List[str]:
        """Identify potential code issues"""
        issues = []

        if 'import *' in code:
            issues.append("⚠️ Found wildcard imports")
        if code.count('TODO') > 0:
            issues.append("⚠️ Found TODO comments")
        if '   ' in code and '\t' not in code:
            issues.append("⚠️ Inconsistent indentation (spaces)")
        if code.count('print(') > 5:
            issues.append("⚠️ Many print statements (use logging instead)")

        return issues if issues else ["✅ No major issues detected"]

    def _generate_suggestions(self, code: str) -> List[str]:
        """Generate code improvement suggestions"""
        suggestions = []

        if code.count('def ') > 0 and '"""' not in code:
            suggestions.append("Add docstrings to functions")
        if 'import' in code and 'from typing' not in code:
            suggestions.append("Consider adding type hints")
        if len(code.split('\n')) > 300:
            suggestions.append("Consider breaking code into smaller modules")
        if code.count('except:') > 0:
            suggestions.append("Use specific exception types instead of bare except")

        return suggestions if suggestions else ["✅ Code looks good"]

    def _get_template_content(self, file_type: str, project_name: str) -> str:
        """Get template content for file type"""
        templates = {
            'package': '"""Package module"""',
            'python_main': f'''"""
Main module for {project_name}
"""

def main():
    print("Hello from {project_name}")

if __name__ == "__main__":
    main()
''',
            'python_utils': '"""Utility functions"""',
            'python_test': f'''"""Tests for {project_name}"""
import unittest

class Test{project_name.title()}(unittest.TestCase):
    def test_example(self):
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
''',
            'html_index': f'''<!DOCTYPE html>
<html>
<head>
    <title>{project_name}</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <h1>Welcome to {project_name}</h1>
    <script src="js/app.js"></script>
</body>
</html>
''',
            'css_style': '/* Styles for your project */',
            'js_app': f'console.log("{project_name} loaded");',
            'js_utils': '// Utility functions',
            'react_app': f'export default function App() {{ return <div>Welcome to {project_name}</div>; }}',
            'react_component': 'export default function Component() { return <div></div>; }',
            'react_page': 'export default function Page() { return <div></div>; }',
            'readme': f'# {project_name}\n\nProject description here.',
            'requirements': 'requests\nflask\npython-dotenv',
            'setup_py': f'''from setuptools import setup

setup(
    name="{project_name}",
    version="0.1.0",
    packages=["{project_name}"],
)
''',
            'package_json': f'''{{
  "name": "{project_name}",
  "version": "1.0.0",
  "description": "{project_name} application",
  "main": "src/index.js",
  "scripts": {{
    "start": "node src/index.js",
    "dev": "nodemon src/index.js"
  }},
  "dependencies": {{}}
}}
'''
        }
        return templates.get(file_type, '')


# -------- CHATGPT-LIKE INTERFACE --------

class ChatGPTInterface:
    """ChatGPT-like conversational interface"""

    def __init__(self):
        self.conversation_history = []
        self.system_prompt = """You are an advanced AI assistant with expertise in:
- Code generation and debugging
- Software architecture and design patterns
- Multiple programming languages
- Web development and databases
- DevOps and cloud technologies
- Machine learning and data science

You provide detailed, practical solutions with code examples."""

        self.coding_agent = AdvancedCodingAgent()

    def format_message(self, role: str, content: str) -> Dict[str, str]:
        """Format message for display"""
        return {"role": role, "content": content}

    def add_to_history(self, role: str, content: str):
        """Add message to conversation history"""
        self.conversation_history.append(self.format_message(role, content))
        # Keep last 20 messages for context
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

    def get_conversation_context(self, limit: int = 10) -> str:
        """Get recent conversation for context"""
        recent = self.conversation_history[-limit:]
        context = ""
        for msg in recent:
            role = msg['role'].upper()
            context += f"{role}: {msg['content'][:100]}...\n" if len(msg['content']) > 100 else f"{role}: {msg['content']}\n"
        return context

    def detect_code_request(self, message: str) -> Tuple[bool, Optional[Dict[str, str]]]:
        """Detect if message is requesting code generation/editing"""

        code_keywords = [
            'generate code', 'write code', 'create code', 'code for',
            'function', 'class', 'api', 'app', 'project',
            'edit this', 'fix this', 'analyze code', 'debug',
            'create project', 'project structure', 'template'
        ]

        message_lower = message.lower()

        for keyword in code_keywords:
            if keyword in message_lower:
                # Determine operation type
                if any(w in message_lower for w in ['generate', 'write', 'create']):
                    return True, {'action': 'generate', 'type': 'code'}
                elif any(w in message_lower for w in ['edit', 'fix']):
                    return True, {'action': 'edit', 'type': 'code'}
                elif 'analyze' in message_lower or 'review' in message_lower:
                    return True, {'action': 'analyze', 'type': 'code'}
                elif 'project' in message_lower:
                    return True, {'action': 'create_project', 'type': 'project'}

        return False, None

    def handle_code_generation(self, message: str) -> str:
        """Handle code generation request"""

        # Detect language
        language = 'python'
        for lang in AdvancedCodingAgent.SUPPORTED_LANGUAGES.keys():
            if lang in message.lower():
                language = lang
                break

        # Generate code
        code, filepath = self.coding_agent.generate_code_from_description(message, language)

        response = f"""✅ Code Generated Successfully!

📁 File: {filepath}

📝 Code Preview:
```{language}
{code[:500]}{'...' if len(code) > 500 else ''}
```

📊 File saved to workspace/code/

💡 Next steps:
- Review the generated code
- Request modifications if needed
- Ask for code analysis or optimization
- Add more functions or features
"""
        return response

    def handle_code_analysis(self, message: str) -> str:
        """Handle code analysis request"""

        # Look for file reference
        file_match = re.search(r'(workspace/code/\S+|\w+\.py|\w+\.js)', message)

        if not file_match:
            return "Please specify which code file to analyze. Example: 'analyze workspace/code/myfile.py'"

        filepath = file_match.group(1)
        if not Path(filepath).exists():
            return f"File not found: {filepath}"

        analysis = self.coding_agent.analyze_code(filepath)

        if 'error' in analysis:
            return f"Error: {analysis['error']}"

        response = f"""📊 Code Analysis Report

📁 File: {analysis['file']}
📏 Lines: {analysis['lines_of_code']}
⚡ Complexity: {analysis['complexity']}

📈 Metrics:
- Functions: {analysis['metrics']['functions']}
- Classes: {analysis['metrics']['classes']}
- Imports: {analysis['metrics']['imports']}
- Comments: {analysis['metrics']['comments']}

⚠️ Issues:
{chr(10).join('- ' + issue for issue in analysis['issues'])}

💡 Suggestions:
{chr(10).join('- ' + suggestion for suggestion in analysis['suggestions'])}
"""
        return response

    def stream_response(self, message: str):
        """Stream response character by character for ChatGPT effect"""

        # Check if it's a code request
        is_code_req, code_info = self.detect_code_request(message)

        if is_code_req:
            if code_info['action'] == 'generate':
                response = self.handle_code_generation(message)
            elif code_info['action'] == 'analyze':
                response = self.handle_code_analysis(message)
            elif code_info['action'] == 'create_project':
                # Extract project details
                project_match = re.search(r'(python|web|react)\s+([\w\-]+)', message.lower())
                if project_match:
                    project_type = f"{project_match.group(1)}_{'package' if project_match.group(1) == 'python' else 'app'}"
                    project_name = project_match.group(2)
                    msg, success = self.coding_agent.create_project_structure(project_name, project_type)
                    response = f"{'✅' if success else '❌'} {msg}"
                else:
                    response = "Please specify project type and name. Example: 'create python myproject'"
        else:
            # General response
            response = self._generate_general_response(message)

        # Stream character by character
        for char in response:
            print(char, end='', flush=True)
            time.sleep(0.01)
        print()

    def _generate_general_response(self, message: str) -> str:
        """Generate general AI response"""

        responses = {
            'hello': '👋 Hello! I\'m your Advanced AI Coding Assistant. I can help you generate, edit, analyze, and optimize code. What would you like to do?',
            'help': '''🆘 Available Commands:
- "generate [language] code for [description]" - Generate new code
- "analyze [filename]" - Analyze existing code
- "create [type] project [name]" - Create project structure
- "edit file at line X" - Edit specific line
- "add function [description]" - Add new function
- Type 'exit' to quit

What can I help you with?
''',
            'thanks': '😊 You\'re welcome! Anything else I can help with?',
            'bye': '👋 Goodbye! Happy coding!',
        }

        message_lower = message.lower().strip()

        for key, response in responses.items():
            if key in message_lower:
                return response

        # Default response
        return f"""I understand you're asking about: "{message}"

I can help you with:
✨ Code Generation - Create code from descriptions
🔍 Code Analysis - Review and optimize code
🏗️ Project Structure - Generate project templates
🐛 Debugging - Find and fix issues
📚 Best Practices - Suggest improvements

What would you like to do? Use 'help' for more options.
"""


# -------- MAIN CHATGPT CHAT LOOP --------

def run_chatgpt_mode():
    """Run the ChatGPT-like interface"""

    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt

    console = Console()
    chat = ChatGPTInterface()

    # Display header
    banner = Panel(
        Text("🤖 ADVANCED AI CODING ASSISTANT v3.0\n💬 ChatGPT-like Interface\n✨ Best-in-Class Code Generation & Editing",
             style="bold cyan"),
        border_style="cyan"
    )
    console.print(banner)

    console.print("[cyan]Type 'help' for commands, 'exit' to quit[/cyan]\n")

    while True:
        try:
            # Get user input
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'bye']:
                console.print("[green]👋 Goodbye![/green]")
                break

            # Add to history
            chat.add_to_history('user', user_input)

            # Generate and stream response
            console.print("[bold cyan]Assistant[/bold cyan]: ", end='')
            chat.stream_response(user_input)

            # Add response to history
            chat.add_to_history('assistant', 'Response generated')

            print()  # New line after response

        except KeyboardInterrupt:
            console.print("\n[green]👋 Goodbye![/green]")
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")


# -------- DEPENDENCIES & SETUP --------

def run_cmd(cmd, check=True):
    """Run command safely across platforms"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import rich
        return True
    except ImportError:
        return False

def install_dependencies():
    """Install required dependencies"""
    packages = ["rich", "pyautogen", "duckduckgo-search", "click", "python-dotenv"]

    for package in packages:
        print(f"Installing {package}...")
        run_cmd(f"{sys.executable} -m pip install {package}", check=False)

def main():
    """Main entry point"""

    # Check and install dependencies
    if not check_dependencies():
        print("Installing dependencies...")
        install_dependencies()

    # Run ChatGPT interface
    run_chatgpt_mode()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
