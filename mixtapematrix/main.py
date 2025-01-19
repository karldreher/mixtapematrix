from .routers.files import File
from .routers.mp3_router import TagRouter
import yaml


class MixtapeMatrix:
    def __init__(self, config: str):
        self.config = config
        self.config_data = self.load_config()

    def load_config(self):
        with open(self.config, "r") as f:
            return yaml.safe_load(f)

    def run(self):
        # TODO: pydantic this thing
        for source in self.config_data.get("sources", []):
            print(f"Copying {source}")
            source_file = File(path=source.get("source_path"))
            destination_file = File(path=source.get("destination_path"))
            exclude_path = source.get("exclude_path", None)
            if source_file.is_dir and source_file.path in destination_file.path:
                raise ValueError(
                    f"Source {source_file.path} is a directory and is a subdirectory of destination {destination_file.path}. This is not allowed, because it will recursively copy the files."
                )

            # print(f"Destination: {destination_file.path}")
            for i in source.get("mp3_files", []):
                for k, v in i.items():
                    router = TagRouter.source(source_file, exclude_path, k, v)
                    for file in set(router):
                        # TODO Debug log this thing
                        # print(f"Copying {file.path} to {destination_file.path}")
                        # TODO: not terribly optimized and could be invalid based on
                        # attribute decisions at class level
                        TagRouter.deeply_copy(file, source_file, destination_file)


def main():
    # TODO obviously get this from the command line, but default to CWD
    matrix = MixtapeMatrix("router.yaml")
    matrix.run()
