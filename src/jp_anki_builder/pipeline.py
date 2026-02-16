class Pipeline:
    def scan(self) -> str:
        return "scan"

    def review(self) -> str:
        return "review"

    def build(self) -> str:
        return "build"

    def run_all(self) -> list[str]:
        return [self.scan(), self.review(), self.build()]
