# Connect6

A PyQt5 Connect6 game with local human-vs-human and human-vs-AI play.

## Requirements

- Python 3.12
- PyQt5
- PyOpenGL is optional. If it is not installed, the game falls back to a static background.

Install the required dependency:

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

On Windows, this also works if `py` is available:

```bash
py -3 main.py
```

## Notes

The deep-learning training pipeline, model checkpoints, generated self-play data,
and local chess records are intentionally excluded from this public repository.
