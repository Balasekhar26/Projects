class SkillGeneralizer:
    @classmethod
    def generalize_commands(cls, commands: list[str]) -> tuple[str, list[str]]:
        """Compares list of commands strings, identifies parameters variables, and returns a templated string."""
        if not commands:
            return "", []
            
        words_list = [cmd.strip().split() for cmd in commands]
        first = words_list[0]
        
        # Check if all commands have the same length
        if not all(len(w) == len(first) for w in words_list):
            # Fallback if lengths vary
            return commands[0], []
            
        templated_words = []
        variables = []
        
        for i in range(len(first)):
            tokens_at_i = {words[i] for words in words_list}
            if len(tokens_at_i) == 1:
                templated_words.append(first[i])
            else:
                templated_words.append("{arg}")
                variables.append(list(tokens_at_i))
                
        return " ".join(templated_words), variables
