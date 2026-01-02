from tabulate import tabulate
import random
import tqdm

# #################################################################################### #
#                           TEAMS
# #################################################################################### #

class Team:
    def __init__(self, name):
        self.name = name
        # Stats
        self.games_played = 0
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.goals_for = 0
        self.goals_against = 0
        self.points = 0
    
    @property
    def goal_difference(self):
        return self.goals_for-self.goals_against


# #################################################################################### #
#                           INFORMATION
# #################################################################################### #
season = 1
teams = [Team("Blue Stars FC"), Team("Hullford FC"), Team("Pitch Disruptors"), Team("Best African Team")]

# #################################################################################### #
#                           TOOLS
# #################################################################################### #

def generate_fixtures(teams:list):
    global fixtures, results
    fixtures = {}
    results = {}
    if len(teams) % 2:
        teams.append('day off')
    n = len(teams)
    for team in teams:
        team.home_counter = 0
        team.away_counter = 0
    matches = []
    all_fixtures = []
    return_matches = []
    for fixture in range(1, n):
        for i in range(n//2):
            for f in all_fixtures[len(all_fixtures)//2-2:len(all_fixtures)//2]:
                for match in f:
                    teams[i].home_counter += 1 if match[0] == teams[i] else 0
                    teams[n -1 - i].away_counter += 1 if match[1] == teams[n -1 - i] else 0
            if not teams[i].home_counter > 1 and not teams[n-1-i].away_counter > 1:
                matches.append((teams[i], teams[n -1 - i]))
                return_matches.append((teams[n -1 - i], teams[i]))
            else:
                matches.append((teams[n -1 - i], teams[i]))
                return_matches.append((teams[i], teams[n -1 - i]))
            
        teams.insert(1, teams.pop())
        all_fixtures.insert(len(all_fixtures)//2, random.sample(matches, k=len(matches)))
        all_fixtures.append(random.sample(return_matches, k=len(return_matches)))
        matches = []
        return_matches = []
    for week, fixture in enumerate(all_fixtures,1):
        fixtures['gw'+str(week)] = fixture

def new_season():
    global gameweek
    for team in teams:
        team.games_played = 0
        team.wins = 0
        team.draws = 0
        team.losses = 0
        team.goals_for = 0
        team.goals_against = 0
        team.points = 0
    generate_fixtures(teams)
    gameweek = 1

new_season()

# #################################################################################### #
#                           MATCH ENGINE
# #################################################################################### #

def simulate_match(home:Team,away:Team):
    home.score = random.randrange(0,5)
    away.score = random.randrange(0,5)
    if home.score > away.score:
        home.points += 3
        home.wins += 1
        away.losses += 1
    elif home.score < away.score:
        away.points += 3
        away.wins += 1
        home.losses += 1
    else:
        home.points += 1
        home.draws += 1
        away.points += 1
        away.draws += 1

    home.games_played += 1
    home.goals_for += home.score
    home.goals_against += away.score
    away.games_played += 1
    away.goals_for += away.score
    away.goals_against += home.score
    return home.score, away.score

def simulate_gameweek():
    games = fixtures['gw'+str(gameweek)]
    results['gw'+str(gameweek)] = []
    for game in games:
        result = simulate_match(game[0], game[1])
        results['gw'+str(gameweek)].append((game[0], result, game[1]))
    fixtures.pop('gw'+str(gameweek))

# #################################################################################### #
#                           MENU NAVIGATOR
# #################################################################################### #
main_menu_options = ["Advance", "Standings", "Fixtures & Results", "Tools", "Quit"]
tools_menu_options = ["Reset League","Back"]

def naviagtor():
    global season, gameweek, stage
    print(f"\nSeason: {season}")
    print(f"Gameweek: {gameweek}\n")
    def show_menu_options(options):
        for num, option in enumerate(options, 1):
            print(f"{num}. {option}")

    def resolve_selected_menu_choice(option):
        pass

    if len(fixtures) < 1:
        main_menu_options[0] = "End Season"
        print(f"The Season has ended!")
    else:
        main_menu_options[0] = "Advance"

    match stage:
        case "main":
            show_menu_options(options=main_menu_options)
            choice = main_menu_options[int(input("\nChoose an option: ")) - 1]
            match choice:
                case "Advance":
                    simulate_gameweek()
                    gameweek += 1
                case "Standings":
                    log_order = enumerate(sorted(teams, key=lambda team: (-team.points, -team.goal_difference,team.name)), 1)
                    log_table = []
                    for rank, team in log_order:
                        log_table.append([rank,team.name,team.games_played,team.wins,team.losses,team.draws,team.goal_difference,team.points])
                    print(f"\n    Log")
                    print(tabulate(log_table, headers=['', "Team","P",'W','L','D','GD','Pts'], tablefmt="simple"),'\n')
                case "Fixtures & Results": 
                    print("\nFIXTURES\n")
                    for key,value in fixtures.items():
                        print(key)
                        for fixture in value:
                            print(fixture[0].name+' v '+fixture[1].name)
                        print()
                    print("\nRESULTS\n")
                    for key,value in results.items():
                        print(key)
                        for result in value:
                            print(result[0].name+f' {result[1][0]}-{result[1][1]} '+result[2].name)
                        print()
                case "Tools":
                    stage = "tools"
                case "Quit":
                    return "quit game"
                case "End Season":
                    season += 1
                    new_season()
                    print("A New Season Awaits!")
                    input("Press Enter to Continue... ")
        case 'tools':
            show_menu_options(options=tools_menu_options)
            choice = tools_menu_options[int(input("\nChoose an option: ")) - 1]
            match choice:
                case "Reset League":
                    new_season()
                    print("Successfully Reset League!")
                    input("Press Enter to Continue...")
                    stage = 'main'
                case "Back":
                    stage = 'main'


# #################################################################################### #
#                               MAIN
# #################################################################################### #
stage = 'main'
def main():
    running = True
    while running:
        if naviagtor():
            break
        
if __name__ == "__main__":
    main()