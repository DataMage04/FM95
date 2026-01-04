from tabulate import tabulate
import random
import tqdm
import math

# #################################################################################### #
#                           TEAMS
# #################################################################################### #

class Team:
    def __init__(self, name):
        self.name = name

        # FINANCES
        self.balance = 0

        # RATINGS
        self.rtg = {
            'Attack' : 0,
            'Midfield' : 0,
            'Defence' : 0,
            'Goalkeeping' : 0,
        }
        self.record = []
        self.players = []

        # STATS
        self.stats = {
            "games_played" : 0,
            "wins" : 0,
            'draws' : 0,
            "losses" : 0,
            'goals_for' : 0,
            'goals_against' : 0,
            'points' : 0,
        }
        # HISTORY
        self.history = {
            'titles' : 0
        }
        
    def calculate_ratings(self):
        gks = 0
        totals = {}

        for key in self.rtg.keys():
            totals[key] = 0

        for player in self.players:
            gks += 1 if player.position == "GK" else 0
            for key, value in player.ratings.items():
                totals[key] += value

        for key in totals:
            if key == "Goalkeeping":
                self.rtg[key] = round(totals[key] / gks) if gks > 0 else 0
            else:
                self.rtg[key] = round(totals[key] / (len(self.players)-gks)) if (len(players)-gks) > 0 else 0

    @property
    def goal_difference(self):
        return self.stats['goals_for']-self.stats['goals_against']
    
    @property
    def form(self):
        value = 0
        for f in self.record[-5:]:
            if f == 'W':
                value += 3/5
            elif f == 'D':
                value += 1/5
        return round(value, 2)
    
    @property
    def rating(self):
        self.calculate_ratings()
        return round(sum(self.rtg.values()) / len(self.rtg))

    @property
    def ratings(self):
        self.calculate_ratings()
        return self.rtg
    
# #################################################################################### #
#                           PLAYERS
# #################################################################################### #

players = []
class Player:
    def __init__(self, name):
        self.name = name
        self.tm = None
        self.position = None

    # RATINGS
        self.ratings = {"Attack" : 50,
        "Midfield" : 50,
        "Defence" : 50,
        "Goalkeeping" : 50}

    @property
    def rating(self):
        return self.ratings.get("Goalkeeping") if self.position == "GK" else round(sum(list(self.ratings.values())[:3])/3)
    
    @property
    def team(self):
        return "Free Agent" if self.tm == None else self.tm.name

namibian_first_names = [
    "Johannes", "Ester", "Frans", "Maria", "Helvi", "Kristofina", "Peneyambeko", 
    "Junias", "Eliaser", "Alfeus", "Nangula", "Twapewa", "Tuhafeni", "Simon", 
    "Usko", "Suoma", "Saima", "Petrus", "Paulus", "Hafeni", "Ndapewa", "Shikongo", 
    "Haidula", "Nghidinwa", "Ababuo", "Abam", "Abana", "Abdulbaki", "Abella", 
    "Abelle", "Abigael", "Adelmiro", "Adelphine", "Adorya", "Afae", "Afiya", 
    "Aggness", "Aghata", "Agnetta", "Aguinaldo", "Crescence", "Creusa", "Crimilde", 
    "Crispine", "Cupidon", "Edebe", "Edgarine", "Edilson", "Edivaldo", "Edmilsa", 
    "Ednah", "Edoghogho", "Behati", "Berhane", "Betje", "Bibi", "Brunelda", 
    "Cazimira", "Cezanne", "Christien", "Jan", "Juane", "Kayla", "Kerina", 
    "Kesiah", "Klara", "Jengo", "Johan", "Junior", "Kabili", "Kai", "Kaikara", 
    "Kaikura", "Kamogelo", "Kian", "Lateef", "Leeto", "Luan", "Luca", "Maghiel", 
    "Mattys", "Nelius", "Philippus", "Ricus", "Ruan", "Ndahafa", "Sakaria", 
    "Lineekela", "Mwahalondjila", "Tulonga", "Fillemon", "Hilen", "Tomas", 
    "Kleopas", "Amalwa", "Ndapandula", "Shapwa", "Mwadhina", "Tuyenikelao", 
    "Iipumbu", "Ndakondja", "Mbinga", "Shilongo"
]

namibian_last_names = [
    "Johannes", "Shikongo", "Paulus", "Petrus", "Andreas", "Namandje", 
    "Katjavivi", "Haufiku", "Nangolo", "Nyambe", "Shilongo", "Sinimbo", 
    "Swartbooi", "Venaani", "Haidula", "Nghidinwa", "Hamutenya", "Iihuhua", 
    "Hamaambo", "Alueendo", "Amungulu", "Huwala", "Mutwa", "Nambundunga", 
    "Namoloh", "Ndaitwah", "Pinehas", "Shaende", "Geingos", "Hauwanga", 
    "Indongo", "Gotthardt", "Haushiku", "Iitula", "Nujoma", "Angula", 
    "Hambuda", "Kugara", "Swart", "Van Wyk", "Nakapunda", "Shifidi", 
    "Mwahalondjila", "Lineekela", "Tulonga", "Fillemon", "Hilen", "Tomas", 
    "Kleopas", "Amalwa", "Ndapandula", "Shapwa", "Mwadhina", "Tuyenikelao", 
    "Iipumbu", "Ndakondja", "Mbinga", "Shilongo", "Nangombe", "Kandjii", 
    "Mukwiilongo", "Shiweda", "Ndemula", "Hangula", "Shifeta", "Ekandjo", 
    "Kamati", "Shanghala", "Uushona", "Nambala", "Shooya", "Mupetami", 
    "Ndjavera", "Kashikola", "Tjivikua", "Munyika", "Shimbuli", "Nankudhu", 
    "Kandume", "Shigwedha", "Mwetupunga", "Nakalemo", "Shikukutu", "Mbangula", 
    "Tjiuoro", "Kandongo", "Shivute", "Nghifikwa", "Mukete", "Shaanika", 
    "Tjitemisa", "Kashuupulwa", "Ndjodhi", "Shikesho", "Mupupa", "Nghilundilua", 
    "Kakololo", "Shilyomunhu", "Nambahu", "Tjiposa", "Mukongo"
]

# Function to generate an attribute value using Gaussian distribution
def generate_attribute(minimum=2, mu=50, sigma=13.2) -> int:
    value = random.gauss(mu=mu, sigma=sigma)  # mean=9, stddev=3.2
    value = max(minimum, min(100, round(value)))  # clamp to 2–20
    return value

# Function to generate a player with weighted attributes using Gaussian distribution
def generate_player(position=None, age=None):

    # Randomly select a Namibian name
    first_name = random.choice(namibian_first_names)
    last_name = random.choice(namibian_last_names)

    if position == "GK":
        gk = generate_attribute()
        dfc = mid = atk = 0
    else:
        gk = 0
        dfc = generate_attribute()
        mid = generate_attribute() 
        atk = generate_attribute()

    player = Player(f'{first_name} {last_name}')
    player.ratings["Attack"] = atk
    player.ratings["Midfield"] = mid
    player.ratings["Defence"] = dfc
    player.ratings["Goalkeeping"] = gk

    # Assign player positions
    positions = {'Attack':'Att', 'Midfield':'Mid', 'Defence':'Def', 'Goalkeeping':'GK'}
    best_position = max(player.ratings, key=player.ratings.get)
    player.position = positions[best_position]

    return player

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
        for stat in team.stats:
            team.stats[stat] = 0
        team.record = []
    generate_fixtures(teams)
    gameweek = 1

def conclude_season():
    winner = log_table[0][1]
    for team in teams:
        if team.name == winner:
            team.history['titles'] += 1
            break

def set_up():
    new_season()
    for i in range(20):
        position = 'GK' if i < 4 else None
        player = generate_player(position=position)
        players.append(player)
    goalkeepers = [player for player in players if player.position == "GK"]
    outfielders =  [player for player in players if player.position != "GK"]
    for team in teams:
        # Assign goalkeeper
        if not goalkeepers:
            raise ValueError("Not enough goalkeepers for all teams")

        gk = random.choice(goalkeepers)
        goalkeepers.remove(gk)

        gk.tm = team
        team.players.append(gk)

        # Assign 3 outfield players
        for _ in range(3):
            if not outfielders:
                raise ValueError("Not enough outfield players")

            player = random.choice(outfielders)
            outfielders.remove(player)

            player.tm = team
            team.players.append(player)

set_up()


# #################################################################################### #
#                           MATCH ENGINE
# #################################################################################### #

def update_table():
    global log_table, log_order
    log_order = enumerate(sorted(teams, key=lambda team: (-team.stats['points'], -team.goal_difference,team.name)), 1)
    log_table = []
    for rank, team in log_order:
        log_table.append([rank,team.name,team.stats['games_played'],team.stats['wins'],team.stats['losses'],team.stats['draws'],team.goal_difference,team.stats['points']])

def record_result(home:Team, away:Team):
    if home.score > away.score:
        home.stats['points'] += 3
        home.stats['wins'] += 1
        away.stats['losses'] += 1
        home.record.append("W")
        away.record.append("L")
    elif home.score < away.score:
        away.stats['points'] += 3
        away.stats['wins'] += 1
        home.stats['losses'] += 1
        home.record.append("L")
        away.record.append("W")
    else:
        home.stats['points'] += 1
        home.stats['draws'] += 1
        away.stats['points'] += 1
        away.stats['draws'] += 1
        home.record.append("D")
        away.record.append("D")

    home.stats['games_played'] += 1
    home.stats['goals_for'] += home.score
    home.stats['goals_against'] += away.score
    away.stats['games_played'] += 1
    away.stats['goals_for'] += away.score
    away.stats['goals_against'] += home.score

def simulate_match(home:Team,away:Team):
    def poisson(lam):
        L = math.exp(-lam)
        k = 0
        p = 1.0

        while p > L:
            k += 1
            p *= random.random()

        return k - 1
    
    HOME_ADVANTAGE = 2
    for team in [home, away]:
        boost = HOME_ADVANTAGE + team.form if team == home else team.form
        team.atk = team.rtg['Attack'] + boost
        team.dfc = team.rtg['Defence'] + boost
        team.mid = team.rtg['Midfield'] + boost
        team.gk = team.rtg['Goalkeeping'] + boost

    BASE_CHANCES = 2.35
    ATK_DEF_SCALE = 40
    MID_SCALE = 80
    MID_DEF_SCALE = 200
    home_atk_effect = 1 + (home.atk - away.dfc)/ATK_DEF_SCALE
    away_atk_effect = 1 + (away.atk - home.dfc)/ATK_DEF_SCALE
    mid_diff = (home.mid-away.mid)/MID_SCALE
    home_xc = BASE_CHANCES * (1 + mid_diff - away.dfc/MID_DEF_SCALE)
    away_xc = BASE_CHANCES * (1 - mid_diff - home.dfc/MID_DEF_SCALE)
    home_xg = home_atk_effect * home_xc
    away_xg = away_atk_effect * away_xc

    home.score = poisson(home_xg)
    away.score = poisson(away_xg)
    record_result(home, away)
    return home.score, away.score

def simulate_gameweek():
    games = fixtures['gw'+str(gameweek)]
    results['gw'+str(gameweek)] = []
    for game in games:
        result = simulate_match(game[0], game[1])
        results['gw'+str(gameweek)].append((game[0], result, game[1]))
    fixtures.pop('gw'+str(gameweek))
    update_table()

# #################################################################################### #
#                           MENU NAVIGATOR
# #################################################################################### #
main_menu_options = ["Advance", "Standings", "Fixtures & Results", "Teams", "Players", "Tools", "Quit"]
players_menu_options = ["Next Page", "Previous Page", "Go To Page","Sort By", "Back"]
tools_menu_options = ["Reset League","Back"]

def naviagtor():
    global season, gameweek, stage, players
    print(f"\nSeason: {season}")
    print(f"Gameweek: {gameweek}\n")

    update_table()

    def show_menu_options(options):
        for num, option in enumerate(options, 1):
            print(f"{num}. {option}")

    if len(fixtures) < 1:
        main_menu_options[0] = "End Season"
        print(f"The Season Has Ended!")
    else:
        main_menu_options[0] = "Advance"

    match stage:
        case "main":
            show_menu_options(options=main_menu_options)
            try:
                choice = main_menu_options[int(input("\nChoose an option: ")) - 1]
            except ValueError:
                choice = main_menu_options[0]
            match choice:
                case "Advance":
                    simulate_gameweek()
                    gameweek += 1
                case "Standings":
                    print(f"\n    Log")
                    print(tabulate(log_table, headers=['', "Team","P",'W','L','D','GD','Pts'], tablefmt="simple"),'\n')
                    input("Press Enter to Continue... ")
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
                    input("Press Enter to Continue... ")
                case "Teams":
                    for team in teams:
                        print(f'\n{team.name.upper()} \nRating: {team.rating}/100 | [Attack:{team.rtg['Attack']} Defence:{team.rtg['Defence']} Midfield:{team.rtg['Midfield']} GoalKeeping:{team.rtg['Goalkeeping']}]')
                        print(f"Record: {team.record}")
                        print(f"Form: {team.form}")
                        print(f"Titles: {team.history['titles']}\n")
                    input("Press Enter to Continue... ")
                case "Players":
                    global PAGE_SIZE, page, max_page
                    PAGE_SIZE = 10
                    page = 0
                    max_page = (len(players) - 1) // PAGE_SIZE
                    stage = 'players'
                case "Tools":
                    stage = "tools"
                case "Quit":
                    return "quit game"
                case "End Season":
                    conclude_season()
                    season += 1
                    new_season()
                    print(f"\nSeason {season-1} has been concluded. A New Season Awaits!")
                    input("Press Enter to Continue... ")
            
        case 'players':
            start = page * PAGE_SIZE
            end = start + PAGE_SIZE
            player_table = []
            for player in players[start:end]:
                player_table.append([player.name, player.position, player.team, player.rating, player.ratings.get("Attack"), player.ratings.get("Midfield"), player.ratings.get("Defence"), player.ratings.get("Goalkeeping")])
            print(tabulate(player_table, headers=['Name', 'Pos', 'Team','Rtg', 'Att', 'Mid', 'Def', 'GK'], tablefmt='simple'), '\n')
            print(f"Page {page + 1} of {max_page + 1}\n")
            show_menu_options(options=players_menu_options)
            choice = players_menu_options[int(input("\nChoose an option: ")) - 1]
            match choice:
                case "Next Page":
                    page += 1 if page < max_page else 0
                case "Previous Page":
                    page -= 1 if page > 0 else 0
                case "Go To Page":
                    p = int(input("\nEnter Page Number: ")) - 1
                    if p <= max_page:
                        page = p
                case 'Sort By':
                    sorters = ['Name', 'Pos', 'Team', "Rtg", "Att", 'Mid', 'Def', 'GK']
                    show_menu_options(options=sorters)
                    choice = sorters[int(input("\nChoose an option: ")) - 1]
                    sort = {'Name':lambda player:player.name, 'Pos':lambda player:player.position, 'Team':lambda player:player.team, 'Rtg':lambda player:-player.rating, "Att":lambda player:-player.ratings["Attack"], 'Mid':lambda player:-player.ratings["Midfield"], 'Def':lambda player:-player.ratings["Defence"], 'GK':lambda player:-player.ratings["Goalkeeping"]}
                    players = sorted(players, key=sort[choice])
                case 'Back':
                    stage = 'main'

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