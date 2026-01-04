from Text_Based_FM import generate_attribute, teams, simulate_match, generate_player
import unittest
import tqdm

def attributes_tester():
    over_90=0
    over_80=0
    over_70=0
    over_60=0
    over_50=0
    over_40=0
    over_30=0
    over_20=0
    over_10=0
    over_0=0
    for i in range(100):
        attr=generate_attribute()
        if attr > 90:
            over_90+=1
        elif attr > 80:
            over_80+=1
        elif attr > 70:
            over_70+=1
        elif attr > 60:
            over_60+=1
        elif attr > 50:
            over_50+=1
        elif attr > 40:
            over_40+=1
        elif attr > 30:
            over_30+=1
        elif attr > 20:
            over_20+=1
        elif attr > 10:
            over_10+=1
        else:
            over_0 +=1
    return [over_0, over_10, over_20, over_30, over_40, over_50, over_60, over_70, over_80, over_90], ['over_0', 'over_10', 'over_20', 'over_30', 'over_40', 'over_50', 'over_60', 'over_70', 'over_80', "over_90"]

class TestMath(unittest.TestCase):
    def test_attributes_generation(self):
        values, headers = attributes_tester()
        print("Tested Attributes Generation")
        print(headers, '\n', values)
    
    def test_matches(self):
        n = 10000
        d = n/100
        home = teams[0]
        away = teams[1]
        for i in range(n):
            simulate_match(home, away)
        print(f"\nSimulated {n} games")
        print(f"Win Percentage: {home.name} - {home.wins/d} : {away.wins/d} - {away.name}")
        print(f"Draw Percentage: {home.name} - {home.draws/d} : {away.draws/d} - {away.name}")
        print(f"Goals/match: {home.name} - {home.goals_for/n} : {away.goals_for/n} - {away.name}")
    
    def test_generate_players(self):
        player = generate_player()
        print(player)
        print("\nGenerated Player")
        print("Player Name", 'position', 'rating', 'ratings')
        print(player.name, player.position, player.rating, player.ratings)


if __name__ == '__main__':
    unittest.main()
