from app.services.providers import LLMProvider, LLMResult


class FakeProvider(LLMProvider):
    """Proveedor de mentira: no hace llamadas de red."""

    name = "fake"

    def __init__(self, text: str = "## Estimación: Test", fail: Exception | None = None):
        super().__init__(model="fake-model")
        self.text = text
        self.fail = fail
        self.calls: list[tuple[str, list]] = []

    def _result(self) -> LLMResult:
        return LLMResult(self.text, self.model, self.name, 100, 0, 20)

    async def complete(self, system, messages):
        self.calls.append((system, messages))
        if self.fail:
            raise self.fail
        return self._result()

    async def stream(self, system, messages):
        self.calls.append((system, messages))
        if self.fail:
            raise self.fail
        for word in self.text.split(" "):
            yield word + " "
        yield self._result()
