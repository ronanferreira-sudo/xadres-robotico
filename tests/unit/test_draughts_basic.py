import draughts
board = draughts.Board(variant='brazilian')
print(board)
for move in board.legal_moves():
    print(move.pdn_move)

