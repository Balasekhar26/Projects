import os
import re

class DomainTagger:
    def __init__(self):
        # Code extension mappings
        self.code_extensions = {
            ".py": "Python",
            ".cpp": "C++",
            ".c": "C",
            ".h": "C/C++ Header",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".sh": "Shell",
            ".html": "HTML",
            ".css": "CSS",
            ".sql": "SQL"
        }

    def detect_domain(self, filepath, content):
        """
        Determines macro and micro classes of a document based on 
        filepath and content hints.
        """
        path_lower = filepath.lower()
        _, ext = os.path.splitext(path_lower)
        
        # 1. Code Checks
        if ext in self.code_extensions:
            return "CODE", self.code_extensions[ext]
            
        # Check if it has lots of programming language keywords and curly braces
        if ext in [".md", ".txt", ""] or not ext:
            # Simple heuristic check for source code in plain text
            lines = content.splitlines()
            if len(lines) > 5:
                brace_count = content.count("{") + content.count("}")
                semicolon_count = content.count(";")
                def_count = len(re.findall(r'\b(def|import|class|func|package|return)\b', content))
                
                if (brace_count > 10 and semicolon_count > 10) or def_count > 5:
                    # Let's check which language it resembles
                    if "def " in content or "import " in content:
                        return "CODE", "Python"
                    elif "include <" in content or "void " in content:
                        return "CODE", "C++"
                    else:
                        return "CODE", "Unknown Code"

        # 2. Check path hints
        if "books" in path_lower:
            return "BOOK", "General Book"
        elif "papers" in path_lower or "arxiv" in path_lower:
            return "PAPER", "Academic"
        elif "conversations" in path_lower or "chat" in path_lower:
            return "CHAT", "Dialogue"
        elif "docs" in path_lower or "documentation" in path_lower:
            return "TECH_DOC", "Technical Specification"
        elif "web" in path_lower:
            return "TEXT", "Web Page"
            
        # 3. Content hints fallback
        # Check paper structures
        if "abstract" in content.lower() and "references" in content.lower() and "introduction" in content.lower():
            return "PAPER", "Academic"
            
        # Check chat logs
        if len(re.findall(r'(?m)^(User|Assistant|Kattappa|System|Human|AI|Q|A):\s', content)) > 3:
            return "CHAT", "Dialogue"
            
        # Check technical docs
        if "api reference" in content.lower() or "installation guide" in content.lower() or "sdk" in content.lower():
            return "TECH_DOC", "Technical Specification"
            
        # Fallback
        return "TEXT", "General Prose"

    def estimate_difficulty(self, macro_class, content):
        """
        Estimates curriculum difficulty (1.0 to 10.0) based on 
        macro category and vocabulary complexity.
        """
        # Base difficulty mappings
        base_diff = {
            "CHAT": 2.0,
            "TEXT": 3.5,
            "BOOK": 5.0,
            "TECH_DOC": 6.5,
            "CODE": 8.0,
            "PAPER": 9.0
        }
        
        diff = base_diff.get(macro_class, 5.0)
        
        # Adjust based on vocab complexity (Unique words / Total words)
        words = re.findall(r'\b[a-zA-Z]+\b', content.lower())
        if len(words) > 50:
            vocab_density = len(set(words)) / len(words)
            # Vocab density typically ranges from 0.2 to 0.7 for standard text
            # Density > 0.5 represents a highly rich/dense register
            if vocab_density > 0.5:
                diff += 1.0
            elif vocab_density < 0.3:
                diff -= 1.0
                
        # Adjust based on average sentence length
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) > 0 and len(words) > 0:
            words_per_sentence = len(words) / len(sentences)
            if words_per_sentence > 25:
                diff += 0.5
            elif words_per_sentence < 10:
                diff -= 0.5
                
        return max(1.0, min(10.0, diff))

    def tag_document(self, doc):
        """Applies macro/micro classification and difficulty scoring to doc."""
        filepath = doc.get("source", "")
        content = doc.get("content", "")
        
        macro, micro = self.detect_domain(filepath, content)
        difficulty = self.estimate_difficulty(macro, content)
        
        doc["macro_class"] = macro
        doc["micro_class"] = micro
        doc["metadata"]["difficulty"] = round(difficulty, 2)
        
        return doc
