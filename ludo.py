"""
- Stochastic: Involving a random variable (in this case, a 6-sided dice roll).
- Heuristic: A mathematical scoring formula used by an AI to guess how "good" 
  a current board layout looks when it cannot see all the way to the end of the game.
- Vector: A multi-element list of scores. Standard Minimax uses a single number, 
  but 3-player games use a 3-element array [Score_1, Score_2, Score_3] to track 
  everyone's unique stance simultaneously.
- Deep Copy: Making a completely independent clone of an object in computer 
  memory so changes to the clone don't alter the actual real live game board.
================================================================================
"""

import random  # Built-in library to generate pseudo-random numbers (used for rolling dice)
import time    # Built-in library to track execution speed up to six decimal places
import copy    # Built-in library used for cloning game states during AI simulations

# ==============================================================================
# CONFIGURATION AND GLOBAL CONSTANTS
# ==============================================================================
# Constants are named variables written in ALL_CAPS that do not change value.
# They map numeric identifiers to players to prevent confusing index errors.
PLAYER_HUMAN = 0  # Index 0 always represents the human user (Red)
PLAYER_AI1   = 1  # Index 1 always represents the first artificial intelligence (Green)
PLAYER_AI2   = 2  # Index 2 always represents the second artificial intelligence (Blue)

# Dictionary mapping numeric IDs to descriptive string literals for UI printouts
PLAYER_NAMES = {
    PLAYER_HUMAN: "Human (Red)",
    PLAYER_AI1:   "AI_1 (Green)",
    PLAYER_AI2:   "AI_2 (Blue)"
}

TRACK_LENGTH = 50  # Total number of shared common tiles layout on the outer board loop (0 to 49)
HOME_SIZE = 3      # Number of private safety pipe tiles at the end of a track layout (Tiles 50, 51, 52)

# Configuration map establishing where each player enters and exits the common track loop.
# This prevents players from colliding right at the spawn zones.
PLAYER_CONFIG = {
    PLAYER_HUMAN: {"start_track": 0,  "exit_track": 49},   # Human loops 0 to 49
    PLAYER_AI1:   {"start_track": 16, "exit_track": 15},   # AI_1 offsets by 16 tiles
    PLAYER_AI2:   {"start_track": 32, "exit_track": 31}    # AI_2 offsets by 32 tiles
}

# Performance tracking counter. Global variables can be accessed by any function.
# This keeps track of how many total simulated board layouts the AI looks at during search.
nodes_visited = 0 


class Token:
    """
    Represents an individual game piece (pawn) on the Ludo board.
    Each player owns exactly 3 tokens.
    """
    def __init__(self, player_id, token_id):
        """
        Constructor method executed automatically when creating a new token object.
        """
        self.player_id = player_id  # Ties the token to its owner (0, 1, or 2)
        self.token_id = token_id    # Differentiates pieces belonging to the same player (1, 2, or 3)
        
        # State machine property tracking the spatial status of the pawn:
        # "YARD"  = Initial starting base. Cannot move unless a 6 is rolled.
        # "TRACK" = Out on the shared board tiles, vulnerable to capture by rivals.
        # "HOME"  = Safe private final track zone. Enemies cannot enter.
        # "GOAL"  = Successfully finished the game course. Locked out from moving permanently.
        self.status = "YARD"        
        self.position = -1          # Stores current integer tile on the board map (-1 if in Yard)

    def __repr__(self):
        """
        Special string representation method. Dictates how this object displays 
        when passed directly into a standard print() function.
        """
        colors = {PLAYER_HUMAN: "R", PLAYER_AI1: "G", PLAYER_AI2: "B"}
        return f"{colors[self.player_id]}{self.token_id}"


class LudoState:
    """
    The master state controller object. It encapsulates the placement of all 9 tokens, 
    tracks relative player progression metrics, and manages turn rotations.
    """
    def __init__(self):
        """
        Initializes a fresh game board with everyone starting from scratch.
        """
        # Dictionary comprehension populating a list of 3 separate Token objects per player
        self.tokens = {
            PLAYER_HUMAN: [Token(PLAYER_HUMAN, i) for i in [1, 2, 3]],
            PLAYER_AI1:   [Token(PLAYER_AI1, i) for i in [1, 2, 3]],
            PLAYER_AI2:   [Token(PLAYER_AI2, i) for i in [1, 2, 3]]
        }
        self.current_turn = PLAYER_HUMAN  # Set initial turn control to the Human player
        
        # Crucial array tracking total step counters (0 to 52) completed by each piece.
        # This is decoupled from absolute position numbers because players spawn at different points.
        # Index 0 is a dummy pad to align tracking with token IDs 1, 2, and 3.
        self.relative_progress = {
            PLAYER_HUMAN: [0, 0, 0, 0], 
            PLAYER_AI1:   [0, 0, 0, 0],
            PLAYER_AI2:   [0, 0, 0, 0]
        }

    def is_terminal(self):
        """
        Evaluates whether the game loop has met its final completion condition.
        Returns:
            bool: True if someone won, False otherwise.
            int/None: Player ID of the winner, or None if the game continues.
        """
        for p in [PLAYER_HUMAN, PLAYER_AI1, PLAYER_AI2]:
            # The all() function returns True only if every single item in the iterable meets the condition
            if all(t.status == "GOAL" for t in self.tokens[p]):
                return True, p  # Found a winner! Halt game execution.
        return False, None      # No player has achieved 3 locked goal pawns yet.

    def get_absolute_track_pos(self, player_id, relative_steps):
        """
        Mathematical mapping function converting relative track steps completed (0-49) 
        into the actual global circular array index on the shared 50-tile track.
        Uses modulo (%) arithmetic to handle looping around past tile 49 back to 0.
        """
        start = PLAYER_CONFIG[player_id]["start_track"]
        return (start + relative_steps) % TRACK_LENGTH

    def get_movable_tokens(self, player_id, roll):
        """
        Validates move options under strict regulatory board constraints.
        Returns a list of array indices corresponding to tokens legally allowed to accept the dice roll.
        """
        movable = []
        for idx, token in enumerate(self.tokens[player_id]):
            if token.status == "GOAL":
                continue # Safeguard: Skip tokens already locked safely in the endzone goal
                
            if token.status == "YARD":
                # Yard Deployment Rule: You can only escape the yard and spawn on tile 0 if you roll a 6
                if roll == 6:
                    movable.append(idx)
            elif token.status in ["TRACK", "HOME"]:
                # Exact Landing Constraint: Tokens cannot overshoot Tile 52. 
                # Move calculation must lead to an exact landing spot <= 52.
                current_relative = self.relative_progress[player_id][idx]
                if current_relative + roll <= 52:
                    movable.append(idx)
        return movable

    def apply_move(self, player_id, token_idx, roll):
        """
        Mutates (changes) the game state board by physically shifting a token forward.
        Handles dynamic status transformations as tokens move between zones.
        """
        token = self.tokens[player_id][token_idx]
        
        # Scenario A: Spawning out of the initial starting yard yard base
        if token.status == "YARD" and roll == 6:
            token.status = "TRACK"
            self.relative_progress[player_id][token_idx] = 0
            token.position = PLAYER_CONFIG[player_id]["start_track"]
            self._handle_capture(player_id, token)  # Check if landing spot kills an enemy piece
            
        # Scenario B: Trailing forward normally across common tracks or private homestreaks
        else:
            self.relative_progress[player_id][token_idx] += roll
            new_rel = self.relative_progress[player_id][token_idx]
            
            if new_rel <= 49:
                token.status = "TRACK"
                token.position = self.get_absolute_track_pos(player_id, new_rel)
                self._handle_capture(player_id, token)  # Run capture physics engine
            elif 50 <= new_rel <= 51:
                token.status = "HOME"
                token.position = new_rel                # Assign safe pipeline location numbers
            elif new_rel == 52:
                token.status = "GOAL"
                token.position = 52                     # Goal target achieved, lock token permanently!

    def _handle_capture(self, moving_player, moving_token):
        """
        Combat Physics: Iterates through rival tracks. If a moving pawn lands on 
        the exact same shared absolute position tile index as an opponent, 
        the opponent's tracking metrics are wiped and they are sent back to the YARD.
        """
        for opp_player in [PLAYER_HUMAN, PLAYER_AI1, PLAYER_AI2]:
            if opp_player == moving_player:
                continue # Skip yourself. Ludo rules do not trigger self-sabotage capturing.
                
            for idx, opp_token in enumerate(self.tokens[opp_player]):
                # Captures can only trigger on the open shared common track layout (Tiles 0 to 49)
                if opp_token.status == "TRACK" and opp_token.position == moving_token.position:
                    opp_token.status = "YARD"
                    opp_token.position = -1
                    self.relative_progress[opp_player][idx] = 0  # Wipe out progress metrics entirely


# ==============================================================================
# MULTIPLAYER MINIMAX & ALPHA-BETA SEARCH ENGINES
# ==============================================================================
def evaluate_state(state):
    """
    THE HEURISTIC EVALUATION FUNCTION:
    Since an AI looking 3 layers deep cannot see the end of a match, it uses this 
    formula to assign numerical utility scores to a board state. Higher points 
    represent a stronger positioning advantage.
    
    Returns a dictionary of utilities (Vector Format): 
    {PLAYER_HUMAN: score, PLAYER_AI1: score, PLAYER_AI2: score}
    """
    scores = {PLAYER_HUMAN: 0.0, PLAYER_AI1: 0.0, PLAYER_AI2: 0.0}
    for p in [PLAYER_HUMAN, PLAYER_AI1, PLAYER_AI2]:
        for idx, token in enumerate(state.tokens[p]):
            if token.status == "GOAL":
                scores[p] += 2000  # Massive payoff reward weight for locking a piece in the goal
            elif token.status == "HOME":
                # Reward safety positioning and scale linearly based on proximity to the goal finish line
                scores[p] += 1000 + (token.position * 10)
            elif token.status == "TRACK":
                # Encourage continuous directional travel velocity to prioritize hunting and layout speed
                scores[p] += 100 + (state.relative_progress[p][idx] * 5)
    return scores

def pure_minimax(state, depth, roll):
    """
    ALGORITHM EXPLANATION - MULTIPLAYER PURE MINIMAX (MAX-N)
    An exhaustive, brute-force search routine. It builds a virtual timeline tree 
    of future turns. It assumes every player will act with total rationality, 
    selecting options that exclusively maximize their own personal end of the 
    returned 3-element score utility vector.
    """
    global nodes_visited
    nodes_visited += 1  # Increment global performance counter for analysis tracking
    
    player = state.current_turn
    is_done, _ = state.is_terminal()
    
    # Base Case: Stop searching if lookahead depth limits hit zero or someone won the game
    if depth == 0 or is_done:
        return evaluate_state(state), None

    movable_indices = state.get_movable_tokens(player, roll)
    
    # Branch Factor Exception Handling: If no tokens can move with this roll, pass turn down the tree
    if not movable_indices:
        next_state = copy.deepcopy(state)                  # Create independent snapshot clone
        next_state.current_turn = (player + 1) % 3         # Rotate turn control cyclically
        res_scores, _ = pure_minimax(next_state, depth - 1, 3) # Recursive lookahead call
        return res_scores, None

    best_token_idx = None
    # Initialize the tracking bounds vector to negative infinity constants
    best_scores = {PLAYER_HUMAN: -float('inf'), PLAYER_AI1: -float('inf'), PLAYER_AI2: -float('inf')}

    # Exhaustively traverse every valid path variation
    for idx in movable_indices:
        branch_state = copy.deepcopy(state)                 # Clone current baseline tree branch node
        branch_state.apply_move(player, idx, roll)          # Simulate the hypothetical move
        branch_state.current_turn = (player + 1) % 3        # Pass simulated future turn control to next agent
        
        # Recursive Dive: call self, reducing depth counter constraint parameter by 1 layer
        scores, _ = pure_minimax(branch_state, depth - 1, 3)
        
        # Max-N Selection Decision: active player chooses the entire branch results vector 
        # solely based on which option yields the highest scalar value for their own identity index.
        if scores[player] > best_scores[player]:
            best_scores = scores
            best_token_idx = idx
            
    return best_scores, best_token_idx

def minimax_alphabeta(state, depth, alpha, beta, roll):
    """
    ALGORITHM EXPLANATION - MULTIPLAYER MINIMAX WITH ALPHA-BETA PRUNING
    This engine follows the same logic as Pure Minimax, but it passes down lower 
    bounds (alpha) and upper bounds (beta) to monitor efficiency thresholds.
    
    Pruning Condition: If an AI branch discovers that a subsequent opponent down 
    the tree can force an outcome that makes this whole path worse than a move the 
    AI already secured earlier, it stops searching this branch (`break`). It discards 
    the rest of the sub-tree, saving huge amounts of memory and processing time.
    """
    global nodes_visited
    nodes_visited += 1  # Increment performance analysis tracking counter
    
    player = state.current_turn
    is_done, _ = state.is_terminal()
    
    # Base Case: return static heuristic metrics if depth limit reached or terminal state hit
    if depth == 0 or is_done:
        return evaluate_state(state), None

    movable_indices = state.get_movable_tokens(player, roll)
    if not movable_indices:
        next_state = copy.deepcopy(state)
        next_state.current_turn = (player + 1) % 3
        res_scores, _ = minimax_alphabeta(next_state, depth - 1, alpha, beta, 3)
        return res_scores, None

    best_token_idx = None
    best_scores = {PLAYER_HUMAN: -float('inf'), PLAYER_AI1: -float('inf'), PLAYER_AI2: -float('inf')}

    for idx in movable_indices:
        branch_state = copy.deepcopy(state)
        branch_state.apply_move(player, idx, roll)
        branch_state.current_turn = (player + 1) % 3
        
        # Run recursive traversal down the optimized pruning search execution thread
        scores, _ = minimax_alphabeta(branch_state, depth - 1, alpha, beta, 3)
        
        if scores[player] > best_scores[player]:
            best_scores = scores
            best_token_idx = idx

        # Vector Pruning Conditions: Update thresholds depending on which player is active
        if player == PLAYER_AI1:
            alpha = max(alpha, best_scores[PLAYER_AI1])  # Alpha monitors the lower bound for AI_1
        elif player == PLAYER_AI2:
            beta = max(beta, best_scores[PLAYER_AI2])   # Beta monitors the ceiling threshold for AI_2
            
        # THE PRUNING INTERCEPT:
        # If upper bound beta drops below lower bound alpha, it means this branch path option 
        # is mathematically guaranteed to be ignored by rational opponents. 
        if beta >= alpha and alpha != -float('inf') and beta != -float('inf'):
            break  # Early Break out of loop. Completely skips generating further deep copy sub-nodes!
            
    return best_scores, best_token_idx


# ==============================================================================
# UI VISUALIZATION RENDER ENGINE
# ==============================================================================
def render_board_natural(state):
    """
    Terminal UI Render Engine: Iterates through all active tokens, looks up their current 
    spatial status data fields, and prints them out to the screen.
    """
    print("\n" + "="*60)
    print("                    --- LIVE LUDO BOARD ---")
    print("="*60)
    
    print("Active Token Placements:")
    token_found = False
    for p in [PLAYER_HUMAN, PLAYER_AI1, PLAYER_AI2]:
        for t in state.tokens[p]:
            if t.status == "YARD":
                print(f"  Token {t} is inside: [YARD]")
                token_found = True
            elif t.status == "TRACK":
                print(f"  Token {t} is out on shared tile: [{t.position}]")
                token_found = True
            elif t.status == "HOME":
                print(f"  Token {t} is inside Private Home tile: [{t.position}]")
                token_found = True
            elif t.status == "GOAL":
                print(f"  Token {t} has locked into: [GOAL TILE 52] 🏁")
                token_found = True
                
    if not token_found:
        print("  No tokens have entered the board layout yet.")
    print("="*60 + "\n")


# ==============================================================================
# MAIN CORE GAME CONTROLLER LOOP
# ==============================================================================
def main():
    """
    Sets up performance modes, manages the turn loop, 
    gathers human player choices, and prints the side-by-side AI engine comparison matrix.
    """
    global nodes_visited
    print("====================================================")
    print("Ludo Board Reference Guide:")
    print(" - Shared Track Tiles: 0 to 49")
    print(" - Private Safety Home Tiles: 50, 51")
    print(" - Completed Locked Goal Tile: 52")
    print("====================================================")
    
    # Prompt user to select mode. Side-by-Side configuration locks random choices to make tests fair.
    use_seed = input("Activate Side-by-Side Algorithm Comparison Mode? (y/n): ").strip().lower()
    if use_seed == 'y':
        random.seed(42)  # Seed 42 locks random choices, forcing the exact same sequence of dice rolls
        print("Comparison Mode Active. AI choices evaluated across both engines simultaneously.")

    game = LudoState()  # Create instance of fresh game layout state object
    AI_DEPTH = 3        # Number of simulated layers ahead the search routines evaluate

    # Main infinite gameplay loop execution block
    while True:
        render_board_natural(game)  # Print current layout to terminal
        
        # Check if terminal game-over conditions are met
        game_over, winner = game.is_terminal()
        if game_over:
            print(f"🏆 {PLAYER_NAMES[winner]} has successfully pathed all pieces to Goal 52! Victory!")
            break

        current_p = game.current_turn
        print(f"🎲 Current Turn: {PLAYER_NAMES[current_p]}")

        # Dice Roll Mechanics: handle human input vs automatic computer rolls
        if current_p == PLAYER_HUMAN:
            input("Press Enter to roll the dice...")
            print("Rolling the dice...")
            time.sleep(0.3)  # Brief sleep delay simulation for user experience layout immersion
            roll = random.choice([1, 2, 3, 4, 5, 6])
            print(f"✨ You rolled a: {roll}!")
        else:
            roll = random.choice([1, 2, 3, 4, 5, 6])
            print(f"✨ {PLAYER_NAMES[current_p]} rolled a: {roll}!")

        # Gather choices list indices
        movable_choices = game.get_movable_tokens(current_p, roll)
        if not movable_choices:
            print("❌ No valid moves possible with this roll. Passing turn.\n")
            game.current_turn = (current_p + 1) % 3  # Shift turn over to next structural player
            continue                                 # Skip remainder of loop iteration block

        chosen_idx = None
        
        # --- HUMAN PLAYER LOGIC SUB-BLOCK ---
        if current_p == PLAYER_HUMAN:
            print("Valid token moves available:")
            for idx in movable_choices:
                t = game.tokens[PLAYER_HUMAN][idx]
                loc = "Yard" if t.status == "YARD" else f"Tile {t.position}"
                print(f"  Input [{t.token_id}] -> Moves piece {t} from {loc}")
            
            # Input sanitization while loop block
            while True:
                user_input = input("Select Token ID: ").strip()
                # Use a list comprehension to check if what the user typed matches a valid movable token ID
                match = [i for i in movable_choices if str(game.tokens[PLAYER_HUMAN][i].token_id) == user_input]
                if match:
                    chosen_idx = match[0]  # Valid choice extracted! Break validation block loop.
                    break
                print("Invalid choice selection.")
                
        # --- ARTIFICIAL INTELLIGENCE SEARCH ENGINE TESTING SUB-BLOCK ---
        else:
            # RUN EXPERIMENT ENGINE 1: Pure Exhaustive Minimax
            nodes_visited = 0                               # Reset global metrics counter tracking property
            t0 = time.perf_counter()                        # Start highly precise system clock counter profile
            _, m_idx = pure_minimax(game, AI_DEPTH, roll)    # Process tree traversal
            t1 = time.perf_counter()                        # Terminate system clock snapshot log
            mm_nodes, mm_time = nodes_visited, (t1 - t0)     # Save dataset values

            # RUN EXPERIMENT ENGINE 2: Alpha-Beta Pruning Optimization variant
            nodes_visited = 0                               # Reset global metrics counter tracking property
            t2 = time.perf_counter()                        # Start clock profile tracking 
            # Send search running passing down negative and positive infinity bounds initialization parameter settings
            _, ab_idx = minimax_alphabeta(game, AI_DEPTH, -float('inf'), float('inf'), roll)
            t3 = time.perf_counter()                        # Terminate system clock snapshot log
            ab_nodes, ab_time = nodes_visited, (t3 - t2)     # Save dataset values

            # Display comparison log straight to terminal instantly
            print(f"\n📊 [AI Engine Comparison Matrix for this Turn]")
            print(f"  | Pure Minimax -> Nodes Checked: {mm_nodes:<5} | Compute Speed: {mm_time:.6f}s")
            print(f"  | Alpha-Beta   -> Nodes Checked: {ab_nodes:<5} | Compute Speed: {ab_time:.6f}s")
            print(f"  | Efficiency Gain: {((mm_nodes - ab_nodes)/max(1, mm_nodes))*100:.1f}% fewer node paths checked.")
            
            # Use Alpha-Beta's optimal choice to move the token forward
            chosen_idx = ab_idx if ab_idx is not None else movable_choices[0]
            print(f"🤖 AI chose to move Token ID: {game.tokens[current_p][chosen_idx].token_id}\n")
            time.sleep(0.4)

        # Apply the final selected move to the real board state layout map variables
        game.apply_move(current_p, chosen_idx, roll)
        game.current_turn = (current_p + 1) % 3  # Safely rotate turn control forward to next cycle agent

# Python initialization idiom ensuring code triggers properly only when executed directly as main script
if __name__ == "__main__":
    main()
