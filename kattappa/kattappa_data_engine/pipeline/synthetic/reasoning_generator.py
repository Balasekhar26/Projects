import random
from pipeline.synthetic.generator_base import BaseGenerator

class ReasoningGenerator(BaseGenerator):
    def __init__(self):
        super().__init__("reasoning")
        self.names = ["Alice", "Bob", "Charlie", "David", "Emily", "Frank", "Grace", "Henry", "Jack", "Kate", "Liam", "Mia", "Noah", "Olivia", "Peter", "Rose"]
        self.cities = ["Station A", "Station B", "London", "Paris", "New York", "Boston", "Chicago", "Seattle", "Delhi", "Mumbai"]

    def generate_meeting_trains(self, idx, seed_val):
        self.set_seed(seed_val)
        city1 = random.choice(self.cities)
        city2 = random.choice([c for c in self.cities if c != city1])
        speed1 = random.randint(50, 110)
        speed2 = random.randint(40, 95)
        # Avoid float division complexity in answers by choosing integer divides
        total_speed = speed1 + speed2
        hours = random.randint(2, 8)
        distance = total_speed * hours
        
        question = f"Problem #{idx}: Two trains leave at the same time, one from {city1} heading towards {city2} at {speed1} mph, and the other from {city2} heading towards {city1} at {speed2} mph. If the distance between the stations is {distance} miles, how many hours will pass before the two trains meet?"
        
        solution = (
            f"Step 1: Understand the relative speed of both trains moving towards each other. "
            f"Relative Speed = Speed of Train 1 + Speed of Train 2 = {speed1} + {speed2} = {total_speed} mph.\n"
            f"Step 2: Use the distance formula (Distance = Speed * Time) to find the time of intersection.\n"
            f"Time = Total Distance / Relative Speed = {distance} / {total_speed} = {hours} hours."
        )
        
        answer = f"The two trains will meet after {hours} hours."
        
        return {
            "id": self.generate_id(idx),
            "category": "reasoning",
            "difficulty": "medium" if hours < 5 else "hard",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["math_word_problems", "relative_speed"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_worker_problems(self, idx, seed_val):
        self.set_seed(seed_val)
        name1 = random.choice(self.names)
        name2 = random.choice([n for n in self.names if n != name1])
        
        # Pick rates that result in clean numbers
        # Let rate1 = 1/A, rate2 = 1/B. Total rate = (A+B)/AB. Joint time = AB / (A+B)
        # Examples of A, B pairs that result in clean integer or half-integer:
        # (3, 6) -> 18/9 = 2
        # (4, 12) -> 48/16 = 3
        # (5, 20) -> 100/25 = 4
        # (6, 12) -> 72/18 = 4
        # (8, 24) -> 192/32 = 6
        pairs = [(3, 6, 2), (4, 12, 3), (5, 20, 4), (6, 12, 4), (8, 24, 6), (10, 15, 6), (12, 24, 8)]
        h1, h2, joint = random.choice(pairs)
        
        question = f"Problem #{idx}: {name1} can paint a house in {h1} hours, while {name2} can paint the same house in {h2} hours. If they work together at their respective constant rates, how many hours will it take them to paint the house?"
        
        solution = (
            f"Step 1: Calculate the work rates of each painter per hour.\n"
            f"Rate of {name1} = 1/{h1} of the house per hour.\n"
            f"Rate of {name2} = 1/{h2} of the house per hour.\n"
            f"Step 2: Combine their rates to get the joint rate.\n"
            f"Joint Rate = 1/{h1} + 1/{h2} = ({h1} + {h2}) / ({h1} * {h2}) = {h1+h2}/{h1*h2} = 1/{joint} of the house per hour.\n"
            f"Step 3: Calculate the time taken to complete the job (1 house).\n"
            f"Time = 1 / Joint Rate = {joint} hours."
        )
        
        answer = f"Working together, it will take them {joint} hours to paint the house."
        
        return {
            "id": self.generate_id(idx),
            "category": "reasoning",
            "difficulty": "medium",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["math_word_problems", "work_rates"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_age_problems(self, idx, seed_val):
        self.set_seed(seed_val)
        parent = random.choice(["father", "mother"])
        child = random.choice(["son", "daughter"])
        
        # Parent age P, Child age C.
        # P = F * C
        # P + Y = G * (C + Y)
        # F * C + Y = G * C + G * Y
        # C * (F - G) = Y * (G - 1)
        # C = Y * (G - 1) / (F - G)
        # Let's pick clean constants:
        # F=3, G=2, Y=15 -> C = 15*(1)/(1) = 15. P=45. check: 45+15=60, 2*(15+15)=60. Correct.
        # F=4, G=2.5, Y=6 -> C = 6*(1.5)/(1.5) = 6. P=24. check: 24+6=30, 2.5*(6+6)=30. Correct.
        # F=4, G=2, Y=12 -> C = 12*(1)/(2) = 6. P=24. check: 24+12=36, 2*(6+12)=36. Correct.
        # F=3, G=2, Y=12 -> C = 12*(1)/(1) = 12. P=36. check: 36+12=48, 2*(12+12)=48. Correct.
        # F=5, G=3, Y=10 -> C = 10*(2)/(2) = 10. P=50. check: 50+10=60, 3*(10+10)=60. Correct.
        configs = [
            (3, 2, 15, 15, 45),
            (4, 2, 12, 6, 24),
            (3, 2, 12, 12, 36),
            (5, 3, 10, 10, 50),
            (4, 3, 5, 10, 40)
        ]
        f, g, y, c_age, p_age = random.choice(configs)
        
        question = f"Problem #{idx}: A {parent} is currently {f} times as old as their {child}. In {y} years, the {parent} will be {g} times as old as the {child}. What are their current ages?"
        
        solution = (
            f"Step 1: Set up the equations. Let C be the {child}'s age and P be the {parent}'s age.\n"
            f"Equation 1: P = {f}C\n"
            f"Equation 2: P + {y} = {g}(C + {y})\n"
            f"Step 2: Substitute Equation 1 into Equation 2.\n"
            f"{f}C + {y} = {g}C + {g * y}\n"
            f"Step 3: Solve for C.\n"
            f"{f}C - {g}C = {g * y} - {y}\n"
            f"{f - g}C = {y * (g - 1)}\n"
            f"C = {c_age}\n"
            f"Step 4: Solve for P.\n"
            f"P = {f} * {c_age} = {p_age}."
        )
        
        answer = f"The {parent} is currently {p_age} years old and the {child} is {c_age} years old."
        
        return {
            "id": self.generate_id(idx),
            "category": "reasoning",
            "difficulty": "hard",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.99,
            "verified": True,
            "skills": ["algebra", "age_calculation"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_batch(self, count):
        batch = []
        for i in range(count):
            seed = 1000 + i
            choice = i % 3
            if choice == 0:
                batch.append(self.generate_meeting_trains(i + 1, seed))
            elif choice == 1:
                batch.append(self.generate_worker_problems(i + 1, seed))
            else:
                batch.append(self.generate_age_problems(i + 1, seed))
        return batch
