from collections.abc import Callable

from app.services.providers import LLMProvider, LLMResult

Responder = Callable[[str, list[dict]], str]


class FakeProvider(LLMProvider):
    """Proveedor de mentira: no hace llamadas de red.

    `responder(system, messages)` decide el texto de la respuesta; por defecto
    devuelve siempre `text`.
    """

    name = "fake"

    def __init__(
        self,
        text: str = "## Estimación: Test",
        fail: Exception | None = None,
        responder: Responder | None = None,
    ):
        super().__init__(model="fake-model")
        self.text = text
        self.fail = fail
        self.responder = responder
        self.calls: list[tuple[str, list]] = []

    def _result(self, system, messages) -> LLMResult:
        text = self.responder(system, messages) if self.responder else self.text
        return LLMResult(text, self.model, self.name, 100, 0, 20)

    async def complete(self, system, messages):
        self.calls.append((system, messages))
        if self.fail:
            raise self.fail
        return self._result(system, messages)

    async def stream(self, system, messages):
        self.calls.append((system, messages))
        if self.fail:
            raise self.fail
        result = self._result(system, messages)
        for word in result.text.split(" "):
            yield word + " "
        yield result
