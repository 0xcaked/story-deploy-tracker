import random

# List of space exploration terms
space_terms = [
    "Astronaut", "Rocket", "Orbit", "Telescope", "Galaxy",
    "Exoplanet", "Lunar", "Spacesuit", "Interstellar", "Satellite",
    "Extraterrestrial", "Black Hole", "Constellation", "Spacewalk",
    "Cosmonaut", "Mars Rover", "Celestial", "Nebula", "Comet",
    "Gravity Assist"
]

# List of quotes related to space exploration
space_quotes = [
    "That's one small step for a man, one giant leap for mankind.",
    "Space exploration is a force of nature unto itself that no other force in society can rival.",
    "The important achievement of Apollo was demonstrating that humanity is not forever chained to this planet and our visions go rather further than that and our opportunities are unlimited.",
    "The Earth is the cradle of humanity, but mankind cannot stay in the cradle forever.",
    "Space exploration is an inherently risky proposition, but the benefits far outweigh the risks.",
    "The universe is probably littered with the one-planet graves of cultures which made the sensible economic decision that there's no good reason to go into space.",
    "The Earth is just the right size to keep humans in and everything else out.",
    "We are all star-stuff.",
    "Space exploration is a force of nature unto itself that no other force in society can rival."
]

def select_random_item(items):
    return random.choice(items)

def encode_message(message):
    encoded_message = ""
    for char in message:
        if char.isalpha():
            encoded_message += chr(ord('a') + (ord(char) - ord('a') + 3) % 26)
        else:
            encoded_message += char
    return encoded_message

def main():
    term = select_random_item(space_terms)
    encoded_term = encode_message(term.lower())
    quote = select_random_item(space_quotes)

    print("Welcome to the Secrets of Space Exploration Code-Breaker!")
    print("Here's a scrambled space exploration term for you to decipher: ", encoded_term)
    
    guess = input("Enter your guess (or 'hint' for a quote): ").strip().lower()
    
    if guess == "hint":
        print("Here's a related quote to help you: ", quote)
    elif guess == term.lower():
        print("Congratulations! You've cracked the code. The term was:", term)
    else:
        print("Oops! That's not correct. Keep trying!")

if __name__ == "__main__":
    main()
