let gameBoard = document.getElementById('game-board');
let ctx = gameBoard.getContext('2d');
let player = {
    x: 0,
    y: 0,
    width: 20,
    height: 20,
    color: 'red'
};
let snakes = [
    {x: 100, y: 100, width: 20, height: 20, color: 'green'},
    {x: 200, y: 200, width: 20, height: 20, color: 'green'}
];
let ladders = [
    {x: 150, y: 150, width: 20, height: 20, color: 'blue'},
    {x: 250, y: 250, width: 20, height: 20, color: 'blue'}
];

function drawGameBoard() {
    ctx.clearRect(0, 0, gameBoard.width, gameBoard.height);
    for (let i = 0; i < snakes.length; i++) {
        ctx.fillStyle = snakes[i].color;
        ctx.fillRect(snakes[i].x, snakes[i].y, snakes[i].width, snakes[i].height);
    }
    for (let i = 0; i < ladders.length; i++) {
        ctx.fillStyle = ladders[i].color;
        ctx.fillRect(ladders[i].x, ladders[i].y, ladders[i].width, ladders[i].height);
    }
    ctx.fillStyle = player.color;
    ctx.fillRect(player.x, player.y, player.width, player.height);
}

function movePlayer(dx, dy) {
    player.x += dx;
    player.y += dy;
    if (player.x < 0 || player.x > gameBoard.width - player.width) {
        player.x = Math.max(0, Math.min(gameBoard.width - player.width, player.x));
    }
    if (player.y < 0 || player.y > gameBoard.height - player.height) {
        player.y = Math.max(0, Math.min(gameBoard.height - player.height, player.y));
    }
}

document.addEventListener('keydown', (e) => {
    switch (e.key) {
        case 'ArrowUp':
            movePlayer(0, -20);
            break;
        case 'ArrowDown':
            movePlayer(0, 20);
            break;
        case 'ArrowLeft':
            movePlayer(-20, 0);
            break;
        case 'ArrowRight':
            movePlayer(20, 0);
            break;
    }
    drawGameBoard();
});

drawGameBoard();
