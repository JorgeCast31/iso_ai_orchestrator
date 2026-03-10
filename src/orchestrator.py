from src.config import validate_env
from src.pipeline import Pipeline


def main():
    validate_env()
    pipeline = Pipeline()
    pipeline.run()


if __name__ == "__main__":
    main()