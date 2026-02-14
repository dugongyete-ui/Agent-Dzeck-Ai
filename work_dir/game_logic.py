import random

def roll_dice():
    return random.randint(1, 6)

def check_snake(player_position):
    snake_positions = [(100, 100), (200, 200)]
    for snake_position in snake_positions:
        if player_position == snake_position:
            return snake_position

def check_ladder(player_position):
    ladder_positions = [(150, 150), (250, 250)]
    for ladder_position in ladder_positions:
        if player_position == ladder_position:
            return ladder_position

def move_player(player_position, roll):
    new_position = (player_position[0] + roll, player_position[1])
    if new_position[0] > 400:
        new_position = (400, new_position[1])
    return new_position

def game_loop(player_position):
    while True:
        roll = roll_dice()
        print(f"Roll: {roll}")
        new_position = move_player(player_position, roll)
        snake_position = check_snake(new_position)
        if snake_position:
            print(f"Snake! Moving back to {snake_position}")
            new_position = snake_position
        ladder_position = check_ladder(new_position)
        if ladder_position:
            print(f"Ladder! Moving up to {ladder_position}")
            new_position = ladder_position
        player_position = new_position
        print(f"New position: {player_position}")
        if player_position[0] == 400:
            print("Game over! You won!")
            break
