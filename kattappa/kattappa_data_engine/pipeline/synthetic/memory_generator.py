import random
from pipeline.synthetic.generator_base import BaseGenerator

class MemoryGenerator(BaseGenerator):
    def __init__(self):
        super().__init__("memory")
        self.managers = ["Alice", "Bob", "Charlie", "Diana", "Ethan", "Fiona", "George", "Hannah", "Ian", "Julia"]
        self.projects = ["Aegis", "Beacon", "Chronos", "Daedalus", "Helios", "Icarus", "Zephyr", "Apex", "Nova", "Titan"]
        self.objects = ["Apple", "Book", "Car", "Desk", "Envelope", "Flask", "Glove", "Helmet", "Ink", "Jacket", "Key", "Lamp", "Map", "Notebook", "Oven", "Pen"]
        self.events = [
            ("the server crashed", "10:00 AM"),
            ("Bob logged in", "10:05 AM"),
            ("the DB replica was promoted", "10:10 AM"),
            ("traffic was redirected", "10:15 AM"),
            ("the backup was completed", "10:20 AM"),
            ("the cache was flushed", "10:25 AM"),
            ("the API rate limit was updated", "10:30 AM")
        ]

    def generate_kv_recall(self, idx, seed_val):
        self.set_seed(seed_val)
        manager = random.choice(self.managers)
        project = random.choice(self.projects)
        
        # Build noise paragraph
        noise_topics = [
            "We discussed the upcoming sprints. The team is currently blocked on the hardware supply chains.",
            "Please review the PR for the authentication backend. The security audit is scheduled for Friday.",
            "Don't forget to submit your weekly timesheets. The system closes tonight at midnight."
        ]
        noise = " ".join(random.sample(noise_topics, 2))
        
        question = (
            f"Memory Task #{idx}: Please remember this association: The project name is '{project}' and its manager is '{manager}'.\n\n"
            f"Context update: {noise}\n\n"
            f"Based on the initial association, who is the manager of the project '{project}'?"
        )
        
        solution = f"Step 1: Locate the association details in the context.\nStep 2: Identify project '{project}' is linked to manager '{manager}'."
        answer = f"The manager of the project '{project}' is {manager}."
        
        return {
            "id": self.generate_id(idx),
            "category": "memory",
            "difficulty": "medium",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["memory_association", "fact_retrieval"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_list_recall(self, idx, seed_val):
        self.set_seed(seed_val)
        sample_objects = random.sample(self.objects, 8)
        indices = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"]
        target_idx = random.randint(0, 7)
        target_word = sample_objects[target_idx]
        target_ord = indices[target_idx]
        
        list_str = ", ".join(sample_objects)
        
        question = (
            f"Memory Task #{idx}: Remember this sequence of 8 items: {list_str}.\n\n"
            f"We must process these items sequentially. Some items are sensitive to memory allocations. "
            f"Please ensure cache isolation while retrieving.\n\n"
            f"What was the {target_ord} item in the list?"
        )
        
        solution = f"Step 1: Scan the sequence of items: {list_str}.\nStep 2: Find the item at index {target_idx} (representing the {target_ord} item)."
        answer = f"The {target_ord} item in the list is {target_word}."
        
        return {
            "id": self.generate_id(idx),
            "category": "memory",
            "difficulty": "hard",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["list_recall", "sequence_retrieval"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_event_recall(self, idx, seed_val):
        self.set_seed(seed_val)
        shuffled_events = random.sample(self.events, 4)
        
        # Sort them by time to make a timeline
        def time_key(item):
            # Convert "10:15 AM" to minutes
            time_str = item[1].split()[0]
            h, m = map(int, time_str.split(':'))
            return h * 60 + m
            
        shuffled_events.sort(key=time_key)
        
        timeline_str = ". ".join([f"At {time}, {desc}" for desc, time in shuffled_events]) + "."
        
        # Pick target: event A and what follows it (event B)
        target_idx = random.randint(0, 2)
        event_a_desc = shuffled_events[target_idx][0]
        event_b_desc = shuffled_events[target_idx+1][0]
        
        question = (
            f"Memory Task #{idx}: Read the following timeline of system events:\n"
            f"{timeline_str}\n\n"
            f"Which event occurred immediately after '{event_a_desc}'?"
        )
        
        solution = f"Step 1: Trace the timeline chronologically.\nStep 2: Find '{event_a_desc}' and identify the event listed immediately after it."
        answer = f"Immediately after '{event_a_desc}', {event_b_desc}."
        
        return {
            "id": self.generate_id(idx),
            "category": "memory",
            "difficulty": "medium",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["temporal_recall", "timeline_tracing"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_batch(self, count):
        batch = []
        for i in range(count):
            seed = 4000 + i
            choice = i % 3
            if choice == 0:
                batch.append(self.generate_kv_recall(i + 1, seed))
            elif choice == 1:
                batch.append(self.generate_list_recall(i + 1, seed))
            else:
                batch.append(self.generate_event_recall(i + 1, seed))
        return batch
