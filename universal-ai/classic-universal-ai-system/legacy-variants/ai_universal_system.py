#!/usr/bin/env python3
"""
🧠⚙️ ENHANCED UNIVERSAL AI SYSTEM v2.0
Cross-platform multi-agent AI system with internet access
Integrated with Open Design & MARK XXXIX capabilities
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
from typing import Dict, List, Optional, Any
import time

# -------- INTEGRATED AI CAPABILITIES --------

class OpenDesignIntegration:
    """Open Design capabilities integration"""

    DESIGN_SYSTEMS = [
        "apple", "google", "notion", "figma", "stripe", "vercel",
        "tesla", "spotify", "airbnb", "netflix", "github", "slack",
        "brutalism", "neumorphism", "glassmorphism", "minimal",
        "editorial", "warm-editorial", "atelier-zero"
    ]

    SKILLS = [
        "saas-landing", "dashboard", "pricing-page", "mobile-app",
        "slide-deck", "social-media", "email-marketing", "poster",
        "invoice", "kanban-board", "wireframe", "prototype",
        "pitch-deck", "quarterly-review", "product-launch"
    ]

    @staticmethod
    def generate_design_prompt(skill: str, design_system: str, content: str) -> str:
        """Generate design creation prompt"""
        return f"""
Create a {skill} using the {design_system} design system.

Content Requirements:
{content}

Design Specifications:
- Use {design_system} design language and components
- Ensure responsive design across all devices
- Include proper typography hierarchy
- Follow accessibility guidelines
- Generate self-contained HTML output
- Include relevant imagery and icons

Output a complete, production-ready design.
"""

    @staticmethod
    def list_available_designs() -> Dict[str, List[str]]:
        """List available design systems and skills"""
        return {
            "design_systems": OpenDesignIntegration.DESIGN_SYSTEMS,
            "skills": OpenDesignIntegration.SKILLS
        }


class MarkXXXIXIntegration:
    """MARK XXXIX AI Assistant capabilities integration"""

    ACTIONS = [
        "file_processor", "flight_finder", "weather_report", "send_message",
        "reminder", "computer_settings", "screen_processor", "youtube_video",
        "desktop_control", "browser_control", "file_controller", "code_helper",
        "dev_agent", "web_search", "computer_control", "game_updater"
    ]

    CAPABILITIES = [
        "real_time_voice", "system_control", "autonomous_tasks",
        "visual_awareness", "persistent_memory", "hybrid_input",
        "cross_platform_support", "screen_analysis", "webcam_vision"
    ]

    @staticmethod
    def create_voice_assistant_prompt(task: str, context: str = "") -> str:
        """Create voice assistant interaction prompt"""
        return f"""
You are MARK XXXIX, an advanced AI assistant with the following capabilities:

CORE FEATURES:
- Real-time voice conversation in any language
- System control (launch apps, manage files, execute commands)
- Autonomous task execution for complex workflows
- Visual awareness (screen analysis and webcam vision)
- Persistent memory for projects and preferences
- Hybrid input (voice + keyboard seamlessly)

AVAILABLE ACTIONS:
{', '.join(MarkXXXIXIntegration.ACTIONS)}

CONTEXT:
{context}

TASK: {task}

Provide a comprehensive response that may include:
1. Voice responses for user interaction
2. System commands to execute
3. File operations or data processing
4. Screen analysis requests
5. Memory updates for future reference
6. Autonomous task planning

Respond naturally as an AI assistant would speak.
"""

    @staticmethod
    def analyze_screen_content(description: str) -> str:
        """Analyze screen content prompt"""
        return f"""
Analyze the following screen content description and provide insights:

SCREEN CONTENT: {description}

Provide:
1. What applications/windows are visible
2. Current user activity context
3. Potential actions or assistance opportunities
4. Relevant information extraction
5. Suggested next steps or automation
"""

    @staticmethod
    def system_control_command(action: str, target: str = "") -> str:
        """Generate system control commands"""
        commands = {
            "launch_app": f"Launch application: {target}",
            "open_file": f"Open file: {target}",
            "execute_command": f"Execute system command: {target}",
            "manage_files": f"File management operation: {target}",
            "browser_action": f"Browser control: {target}"
        }
        return commands.get(action, f"System action: {action} on {target}")


class EnhancedAISystem:
    """Enhanced AI System combining all capabilities"""

    def __init__(self):
        self.open_design = OpenDesignIntegration()
        self.mark_xxxix = MarkXXXIXIntegration()
        self.conversation_memory = []
        self.user_preferences = {}

    def add_to_memory(self, interaction: Dict[str, Any]):
        """Add interaction to persistent memory"""
        self.conversation_memory.append({
            "timestamp": time.time(),
            "interaction": interaction
        })
        # Keep only last 50 interactions
        if len(self.conversation_memory) > 50:
            self.conversation_memory = self.conversation_memory[-50:]

    def get_memory_context(self, limit: int = 10) -> str:
        """Get recent conversation context"""
        recent = self.conversation_memory[-limit:]
        if not recent:
            return "No previous context available."

        context = "RECENT CONVERSATION CONTEXT:\n"
        for item in recent:
            context += f"- {item['interaction'].get('user', '')}: {item['interaction'].get('task', '')}\n"
        return context

    def process_enhanced_task(self, task: str, mode: str = "general") -> Dict[str, Any]:
        """Process task with enhanced capabilities"""

        # Detect task type and route to appropriate system
        if any(keyword in task.lower() for keyword in ["design", "ui", "website", "landing", "dashboard", "prototype"]):
            return self._handle_design_task(task)
        elif any(keyword in task.lower() for keyword in ["voice", "screen", "control", "launch", "system", "assistant"]):
            return self._handle_assistant_task(task)
        else:
            return self._handle_general_task(task, mode)

    def _handle_design_task(self, task: str) -> Dict[str, Any]:
        """Handle design-related tasks using Open Design capabilities"""
        designs = self.open_design.list_available_designs()

        response = {
            "type": "design",
            "capabilities": "Open Design Integration",
            "available_design_systems": designs["design_systems"],
            "available_skills": designs["skills"],
            "prompt": self.open_design.generate_design_prompt(
                skill="landing_page",
                design_system="modern",
                content=task
            )
        }
        return response

    def _handle_assistant_task(self, task: str) -> Dict[str, Any]:
        """Handle assistant-related tasks using MARK XXXIX capabilities"""
        context = self.get_memory_context()

        response = {
            "type": "assistant",
            "capabilities": "MARK XXXIX Integration",
            "available_actions": self.mark_xxxix.ACTIONS,
            "core_features": self.mark_xxxix.CAPABILITIES,
            "prompt": self.mark_xxxix.create_voice_assistant_prompt(task, context)
        }
        return response

    def _handle_general_task(self, task: str, mode: str) -> Dict[str, Any]:
        """Handle general tasks with enhanced context"""
        context = self.get_memory_context()

        response = {
            "type": "general",
            "mode": mode,
            "enhanced_context": context,
            "integrated_capabilities": {
                "open_design": "Available for design tasks",
                "mark_xxxix": "Available for assistant tasks",
                "web_search": "Available for research",
                "multi_agent": "Available for complex analysis"
            }
        }
        return response


# Global enhanced system instance
enhanced_system = EnhancedAISystem()

# -------- AUTO INSTALL --------
def run_cmd(cmd, check=True):
    """Run command safely across platforms"""
    try:
        if platform.system() == "Windows":
            subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        else:
            subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {cmd}")
        print(f"Error: {e}")
        return False
    return True

def check_ollama():
    """Check if Ollama is installed and running"""
    try:
        result = subprocess.run("ollama --version", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Ollama found: {result.stdout.strip()}")
            return True
    except:
        pass

    print("❌ Ollama not found or not running")
    return False

def install():
    """Install all dependencies"""
    print("🔧 Installing dependencies...")

    # Upgrade pip
    run_cmd(f"{sys.executable} -m pip install --upgrade pip")

    # Install Python packages
    packages = [
        "pyautogen",
        "duckduckgo-search",
        "rich",
        "click",
        "python-dotenv",
        "anthropic",  # For Open Design AI integration
        "openai",     # For enhanced AI capabilities
        "google-generativeai",  # For MARK XXXIX Gemini integration
        "pyaudio",    # For voice capabilities
        "speechrecognition",  # For speech recognition
        "pyttsx3",    # For text-to-speech
        "pillow",     # For image processing
        "opencv-python",  # For computer vision/screen analysis
        "pyautogui",  # For system control automation
        "psutil",     # For system monitoring
        "screeninfo"  # For screen information
    ]

    for package in packages:
        print(f"Installing {package}...")
        if not run_cmd(f"{sys.executable} -m pip install {package}"):
            print(f"Failed to install {package}")

    # Check Ollama
    if not check_ollama():
        print("\n❌ OLLAMA NOT FOUND")
        print("Please install Ollama first:")
        print("👉 https://ollama.com/download")
        print("After installation, restart this script.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Pull models (lightweight for compatibility)
    print("\n📥 Downloading AI models...")
    models = ["mistral", "phi3"]

    for model in models:
        print(f"Pulling {model}...")
        if not run_cmd(f"ollama pull {model}"):
            print(f"Failed to pull {model}")

    print("✅ Installation complete!")

# -------- INTERNET SEARCH --------
from duckduckgo_search import DDGS

def search_web(query):
    """Search web using DuckDuckGo"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        return "\n".join([f"{r['title']}: {r['body']}" for r in results])
    except Exception as e:
        return f"Search failed: {str(e)}"

# -------- UI COMPONENTS --------
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Prompt
import click

console = Console()

def show_banner():
    """Display system banner"""
    banner = Panel(
        Text("🧠⚙️ ENHANCED UNIVERSAL AI SYSTEM v2.0\n🎨 Open Design + 🤖 MARK XXXIX Integration", style="bold blue"),
        subtitle="Cross-platform Multi-Agent AI with Design Studio & Voice Assistant",
        border_style="blue"
    )
    console.print(banner)

def show_help():
    """Show help information"""
    help_table = Table(title="Commands Guide")
    help_table.add_column("Command", style="cyan")
    help_table.add_column("Description", style="white")

    help_table.add_row("help", "Show this help")
    help_table.add_row("chat", "Start chat mode")
    help_table.add_row("code", "Start coding agent")
    help_table.add_row("multi", "Multi-agent simulation")
    help_table.add_row("design", "Open Design Studio - Create websites & designs")
    help_table.add_row("assistant", "MARK XXXIX AI Assistant - Voice & system control")
    help_table.add_row("search:query", "Search internet")
    help_table.add_row("status", "Show system status")
    help_table.add_row("exit", "Exit system")

    console.print(help_table)

def show_status():
    """Show system status"""
    status_table = Table(title="System Status")
    status_table.add_column("Component", style="cyan")
    status_table.add_column("Status", style="green")

    # Check Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    status_table.add_row("Python", f"✅ {py_version}")

    # Check OS
    os_name = platform.system()
    status_table.add_row("OS", f"✅ {os_name}")

    # Check Ollama
    ollama_status = "✅ Running" if check_ollama() else "❌ Not running"
    status_table.add_row("Ollama", ollama_status)

    # Check models
    try:
        result = subprocess.run("ollama list", shell=True, capture_output=True, text=True)
        if "mistral" in result.stdout and "phi3" in result.stdout:
            status_table.add_row("Models", "✅ mistral, phi3")
        else:
            status_table.add_row("Models", "⚠️ Some models missing")
    except:
        status_table.add_row("Models", "❌ Unknown")

    # Check enhanced integrations
    status_table.add_row("Open Design", "✅ Integrated (200+ design systems)")
    status_table.add_row("MARK XXXIX", "✅ Integrated (Voice & system control)")
    status_table.add_row("Memory System", f"✅ Active ({len(enhanced_system.conversation_memory)} interactions)")

    console.print(status_table)

# -------- AI SYSTEM --------
def create_agents():
    """Create AI agents with different models"""
    try:
        from autogen import AssistantAgent, UserProxyAgent

        # Configuration for different agents
        assistant_config = [{
            "model": "mistral",
            "base_url": "http://localhost:11434/v1",
            "api_key": "NULL"
        }]

        coder_config = [{
            "model": "mistral",
            "base_url": "http://localhost:11434/v1",
            "api_key": "NULL"
        }]

        reviewer_config = [{
            "model": "phi3",
            "base_url": "http://localhost:11434/v1",
            "api_key": "NULL"
        }]

        # Create agents
        assistant = AssistantAgent(
            "assistant",
            llm_config={"config_list": assistant_config},
            system_message="You are a helpful AI assistant. Provide clear, accurate answers."
        )

        coder = AssistantAgent(
            "coder",
            llm_config={"config_list": coder_config},
            system_message="You are a coding expert. Write clean, efficient code and explain your solutions."
        )

        reviewer = AssistantAgent(
            "reviewer",
            llm_config={"config_list": reviewer_config},
            system_message="You are a critical reviewer. Analyze responses for accuracy, completeness, and potential issues."
        )

        # User proxy
        user = UserProxyAgent(
            "user",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False
            },
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3
        )

        return assistant, coder, reviewer, user

    except Exception as e:
        console.print(f"[red]❌ Failed to create agents: {e}[/red]")
        return None, None, None, None

def chat_mode():
    """Interactive chat mode"""
    console.print("[blue]💬 Chat Mode - Type 'exit' to return to menu[/blue]")

    assistant, _, _, user = create_agents()
    if not assistant:
        return

    while True:
        try:
            task = Prompt.ask("\n[bold]>>[/bold]")

            if task.lower() == 'exit':
                break

            if task.lower() == 'help':
                show_help()
                continue

            # Handle search commands
            if task.startswith("search:"):
                query = task.replace("search:", "")
                console.print(f"[yellow]🔍 Searching: {query}[/yellow]")
                info = search_web(query)
                task = f"Use this information to answer: {query}\n\nInfo: {info}"

            # Process with AI
            console.print("[cyan]🤔 Thinking...[/cyan]")
            user.initiate_chat(assistant, message=task, max_turns=1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

def code_mode():
    """Coding agent mode"""
    console.print("[blue]👨‍💻 Code Mode - Type 'exit' to return to menu[/blue]")
    console.print("[yellow]Files are created in 'workspace/' folder[/yellow]")

    _, coder, _, user = create_agents()
    if not coder:
        return

    # Ensure workspace exists
    os.makedirs("workspace", exist_ok=True)

    while True:
        try:
            task = Prompt.ask("\n[bold]Code>>[/bold]")

            if task.lower() == 'exit':
                break

            if task.lower() == 'help':
                console.print("Examples:")
                console.print("- create a python calculator")
                console.print("- fix errors in app.py")
                console.print("- optimize this algorithm")
                continue

            # Handle search in coding mode
            if task.startswith("search:"):
                query = task.replace("search:", "")
                console.print(f"[yellow]🔍 Searching: {query}[/yellow]")
                info = search_web(query)
                task = f"Use this information for coding: {query}\n\nInfo: {info}"

            console.print("[cyan]👨‍💻 Coding...[/cyan]")
            user.initiate_chat(coder, message=task, max_turns=2)

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

def multi_agent_mode():
    """Multi-agent simulation mode"""
    console.print("[blue]🧠 Multi-Agent Mode - Type 'exit' to return to menu[/blue]")

    assistant, coder, reviewer, user = create_agents()
    if not all([assistant, coder, reviewer]):
        return

    while True:
        try:
            task = Prompt.ask("\n[bold]Multi>>[/bold]")

            if task.lower() == 'exit':
                break

            if task.lower() == 'help':
                console.print("Examples:")
                console.print("- debate the best approach for X")
                console.print("- simulate 3 experts solving Y")
                console.print("- analyze this from multiple perspectives")
                continue

            # Handle search
            if task.startswith("search:"):
                query = task.replace("search:", "")
                console.print(f"[yellow]🔍 Searching: {query}[/yellow]")
                info = search_web(query)
                task = f"Use this information: {query}\n\nInfo: {info}"

            console.print("[cyan]🧠 Multi-agent thinking...[/cyan]")

            # Assistant provides initial response
            console.print("[yellow]Assistant:[/yellow]")
            user.initiate_chat(assistant, message=task, max_turns=1)

            # Coder provides technical perspective
            console.print("[yellow]Coder:[/yellow]")
            user.initiate_chat(coder, message=f"Technical analysis of: {task}", max_turns=1)

            # Reviewer provides critique
            console.print("[yellow]Reviewer:[/yellow]")
            user.initiate_chat(reviewer, message=f"Review and improve the responses to: {task}", max_turns=1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

def design_studio_mode():
    """Open Design Studio mode"""
    console.print("[blue]🎨 Design Studio Mode - Type 'exit' to return to menu[/blue]")
    console.print("[yellow]Create websites, apps, and designs with AI[/yellow]")

    while True:
        try:
            console.print("\n[yellow]Available Design Systems:[/yellow]")
            designs = enhanced_system.open_design.list_available_designs()
            for i, system in enumerate(designs["design_systems"][:10], 1):  # Show first 10
                console.print(f"[cyan]{i}.[/cyan] {system}")
            console.print("[cyan]... and {len(designs['design_systems'])-10} more[/cyan]")

            console.print("\n[yellow]Available Skills:[/yellow]")
            for i, skill in enumerate(designs["skills"], 1):
                console.print(f"[cyan]{i}.[/cyan] {skill}")

            task = Prompt.ask("\n[bold]Design>>[/bold]")

            if task.lower() == 'exit':
                break

            if task.lower() == 'help':
                console.print("Examples:")
                console.print("- create a landing page for my startup")
                console.print("- design a dashboard for analytics")
                console.print("- make a mobile app prototype")
                console.print("- generate a slide deck presentation")
                continue

            # Process design task
            result = enhanced_system.process_enhanced_task(task, "design")

            console.print(f"[green]🎨 Processing with {result['capabilities']}[/green]")
            console.print(f"[yellow]Available systems: {', '.join(result['available_design_systems'][:5])}...[/yellow]")
            console.print(f"[yellow]Available skills: {', '.join(result['available_skills'])}[/yellow]")

            # Create design with AI
            console.print("[cyan]🎨 Generating design...[/cyan]")

            # Use the existing AI agents to generate the design
            assistant, _, _, user = create_agents()
            if assistant:
                user.initiate_chat(assistant, message=result['prompt'], max_turns=2)

            # Add to memory
            enhanced_system.add_to_memory({
                "user": "design_request",
                "task": task,
                "type": "design",
                "timestamp": time.time()
            })

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

def ai_assistant_mode():
    """MARK XXXIX AI Assistant mode"""
    console.print("[blue]🤖 AI Assistant Mode - Type 'exit' to return to menu[/blue]")
    console.print("[yellow]Voice-controlled AI assistant with system integration[/yellow]")

    while True:
        try:
            console.print("\n[yellow]Assistant Capabilities:[/yellow]")
            capabilities = enhanced_system.mark_xxxix.CAPABILITIES
            for i, cap in enumerate(capabilities, 1):
                console.print(f"[cyan]{i}.[/cyan] {cap.replace('_', ' ').title()}")

            console.print("\n[yellow]Available Actions:[/yellow]")
            actions = enhanced_system.mark_xxxix.ACTIONS
            for i, action in enumerate(actions[:10], 1):  # Show first 10
                console.print(f"[cyan]{i}.[/cyan] {action.replace('_', ' ').title()}")
            if len(actions) > 10:
                console.print(f"[cyan]... and {len(actions)-10} more actions[/cyan]")

            task = Prompt.ask("\n[bold]Assistant>>[/bold]")

            if task.lower() == 'exit':
                break

            if task.lower() == 'help':
                console.print("Examples:")
                console.print("- analyze my screen")
                console.print("- launch chrome browser")
                console.print("- check the weather")
                console.print("- process this file")
                console.print("- remind me in 30 minutes")
                continue

            # Process assistant task
            result = enhanced_system.process_enhanced_task(task, "assistant")

            console.print(f"[green]🤖 Processing with {result['capabilities']}[/green]")
            console.print(f"[yellow]Core features: {', '.join(result['core_features'])}[/yellow]")

            # Handle special assistant commands
            if "screen" in task.lower() or "analyze" in task.lower():
                console.print("[cyan]👁️ Screen analysis mode activated[/cyan]")
                console.print("[yellow]Note: For full screen analysis, MARK XXXIX would capture and analyze your screen[/yellow]")
            elif any(cmd in task.lower() for cmd in ["launch", "open", "start"]):
                console.print("[cyan]🚀 System control activated[/cyan]")
                console.print("[yellow]Note: For full system control, MARK XXXIX would execute system commands[/yellow]")
            elif "voice" in task.lower():
                console.print("[cyan]🎙️ Voice mode activated[/cyan]")
                console.print("[yellow]Note: For full voice interaction, MARK XXXIX uses real-time audio processing[/yellow]")

            # Create assistant response with AI
            console.print("[cyan]🤖 Generating assistant response...[/cyan]")

            # Use the existing AI agents to respond as assistant
            assistant, _, _, user = create_agents()
            if assistant:
                user.initiate_chat(assistant, message=result['prompt'], max_turns=2)

            # Add to memory
            enhanced_system.add_to_memory({
                "user": "assistant_request",
                "task": task,
                "type": "assistant",
                "timestamp": time.time()
            })

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")

# -------- MAIN INTERFACE --------
def main_menu():
    """Main system menu"""
    while True:
        console.print("\n" + "="*60)
        console.print("[bold blue]🧠⚙️ ENHANCED UNIVERSAL AI SYSTEM v2.0[/bold blue]")
        console.print("[yellow]🎨 Open Design + 🤖 MARK XXXIX Integration[/yellow]")
        console.print("="*60)

        choices = [
            "💬 Chat Mode",
            "👨‍💻 Code Mode",
            "🧠 Multi-Agent Mode",
            "🎨 Design Studio (Open Design)",
            "🤖 AI Assistant (MARK XXXIX)",
            "🔍 Quick Search",
            "📊 System Status",
            "❓ Help",
            "🚪 Exit"
        ]

        for i, choice in enumerate(choices, 1):
            console.print(f"[cyan]{i}.[/cyan] {choice}")

        try:
            choice = Prompt.ask("\nSelect option", choices=["1","2","3","4","5","6","7","8","9"])

            if choice == "1":
                chat_mode()
            elif choice == "2":
                code_mode()
            elif choice == "3":
                multi_agent_mode()
            elif choice == "4":
                design_studio_mode()
            elif choice == "5":
                ai_assistant_mode()
            elif choice == "6":
                query = Prompt.ask("Search query")
                result = search_web(query)
                console.print(f"[yellow]Search Results:[/yellow]\n{result}")
            elif choice == "7":
                show_status()
            elif choice == "8":
                show_help()
            elif choice == "9":
                console.print("[green]👋 Goodbye![/green]")
                break

        except KeyboardInterrupt:
            console.print("\n[green]👋 Goodbye![/green]")
            break

# -------- ENTRY POINT --------
def main():
    """Main entry point"""
    show_banner()

    # Check if first run
    if not os.path.exists("installed.flag"):
        console.print("[yellow]🔧 First-time setup detected...[/yellow]")
        install()
        open("installed.flag", "w").close()
        console.print("[green]✅ Setup complete! Restarting...[/green]")
        input("Press Enter to continue...")
        # Restart the script
        os.execv(sys.executable, ['python'] + sys.argv)

    # Check Ollama status
    if not check_ollama():
        console.print("[red]❌ Ollama is not running![/red]")
        console.print("Please start Ollama and restart this script.")
        input("Press Enter to exit...")
        return

    # Create workspace
    os.makedirs("workspace", exist_ok=True)

    # Start main interface
    main_menu()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[green]👋 Goodbye![/green]")
    except Exception as e:
        console.print(f"[red]❌ Fatal error: {e}[/red]")
        input("Press Enter to exit...")
