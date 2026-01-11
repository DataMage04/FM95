import random
def generate_attribute(minimum=2, mu=50, sigma=13.2) -> int:
    value = random.gauss(mu=mu, sigma=sigma)  # mean=9, stddev=3.2
    value = max(minimum, min(100, round(value)))  # clamp to 2–20
    return value

print(generate_attribute(mu=30, sigma=10))