from .routers.files import File, FileRouter
from .routers.mp3_router import TagRouter
import yaml


class MixtapeMatrix:
    def __init__(self, config: str):
        self.config = config
        self.config_data = self.load_config()

    def load_config(self):
        with open(self.config, 'r') as f:
            return yaml.safe_load(f)

    def run(self):
        # TODO: pydantic this thing
        for source in self.config_data.get('sources', []):
            print(f"Copying {source}")
            source_file = File(path=source.get('source_path'))
            destination_file = File(path=source.get('destination_path'))
            print(f"Destination: {destination_file.path}")
            for i in source.get('mp3_files', []):
                for k, v in i.items():
                    router = TagRouter.source(source_file, k, v)
                    # TODO: didn't catch genre yet, could be a file problem
                    for file in router:
                        # TODO Debug log this thing
                        print(f"Copying {file.path} to {destination_file.path}")
                        # TODO: not terribly optimized and could be invalid based on
                        # attribute decisions at class level
                        TagRouter.deeply_copy(file, destination_file)

                    

def main():
    matrix = MixtapeMatrix("router.yaml")
    matrix.run()
