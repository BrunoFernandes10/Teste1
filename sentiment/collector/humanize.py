"""Motor de comportamento humano.

Todo movimento do sistema passa por aqui. O objetivo nao e apenas "esperar um
pouco": e reproduzir a assinatura temporal e motora de uma pessoa lendo um
perfil — pausas com cauda longa, leitura proporcional ao tamanho do texto,
mouse em curva, rolagem com desaceleracao e a ocasional volta atras.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

# Pausas base em segundos (mediana, dispersao) antes do fator de ritmo.
PAUSES = {
    "micro": (0.35, 0.25),      # entre duas acoes encadeadas
    "curta": (1.1, 0.4),        # depois de um clique simples
    "media": (2.6, 0.5),        # trocar de contexto na tela
    "longa": (5.5, 0.6),        # abrir uma publicacao, esperar carregar
    "reflexao": (9.0, 0.7),     # a pessoa parou pra pensar / se distraiu
}

# Velocidade de leitura humana: palavras por minuto.
WPM_MEDIA = 220
WPM_DESVIO = 45


@dataclass
class Human:
    """Gera os tempos e os gestos da sessao."""

    pace: float = 1.0
    rng: random.Random = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random()

    # -- tempo ------------------------------------------------------------
    def delay(self, kind: str = "curta") -> float:
        """Sorteia uma pausa log-normal (cauda longa, como gente de verdade)."""
        median, sigma = PAUSES.get(kind, PAUSES["curta"])
        value = self.rng.lognormvariate(0.0, sigma) * median * self.pace
        return max(0.08, min(value, median * 6 * self.pace))

    async def pause(self, kind: str = "curta") -> float:
        seconds = self.delay(kind)
        await asyncio.sleep(seconds)
        return seconds

    def reading_time(self, text: str, minimum: float = 1.2) -> float:
        """Tempo de leitura proporcional ao volume de texto."""
        words = max(1, len(str(text or "").split()))
        wpm = max(90.0, self.rng.gauss(WPM_MEDIA, WPM_DESVIO))
        seconds = (words / wpm) * 60.0
        # Releitura ocasional: 15% das vezes a pessoa volta e le de novo.
        if self.rng.random() < 0.15:
            seconds *= self.rng.uniform(1.3, 1.9)
        return max(minimum, seconds) * self.pace

    async def read(self, text: str, minimum: float = 1.2) -> float:
        seconds = self.reading_time(text, minimum)
        await asyncio.sleep(seconds)
        return seconds

    async def maybe_distract(self, probability: float = 0.12) -> float:
        """De vez em quando a pessoa olha o celular / atende alguem."""
        if self.rng.random() < probability:
            return await self.pause("reflexao")
        return 0.0

    # -- gestos -----------------------------------------------------------
    def _bezier(self, start: tuple[float, float], end: tuple[float, float], steps: int):
        """Curva de Bezier quadratica com ponto de controle deslocado."""
        cx = (start[0] + end[0]) / 2 + self.rng.uniform(-120, 120)
        cy = (start[1] + end[1]) / 2 + self.rng.uniform(-90, 90)
        for i in range(1, steps + 1):
            t = i / steps
            # suavizacao ease-in-out para nao ter velocidade constante
            t = t * t * (3 - 2 * t)
            x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * cx + t**2 * end[0]
            y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * cy + t**2 * end[1]
            yield x + self.rng.uniform(-1.2, 1.2), y + self.rng.uniform(-1.2, 1.2)

    async def move_mouse(self, page, x: float, y: float, origin: Optional[tuple[float, float]] = None) -> None:
        """Move o cursor em curva, com micro-tremor, ate (x, y)."""
        start = origin or (self.rng.uniform(80, 700), self.rng.uniform(80, 500))
        steps = self.rng.randint(14, 28)
        for px, py in self._bezier(start, (x, y), steps):
            try:
                await page.mouse.move(px, py)
            except Exception:
                return
            await asyncio.sleep(self.rng.uniform(0.006, 0.022) * self.pace)

    async def hover(self, locator, page=None) -> None:
        """Aproxima o mouse do elemento antes de qualquer clique."""
        try:
            box = await locator.bounding_box()
            if box and page is not None:
                target_x = box["x"] + box["width"] * self.rng.uniform(0.3, 0.7)
                target_y = box["y"] + box["height"] * self.rng.uniform(0.3, 0.7)
                await self.move_mouse(page, target_x, target_y)
            await locator.hover(timeout=5000)
        except Exception:
            pass
        await self.pause("micro")

    async def click(self, locator, page=None) -> None:
        """Clique precedido de aproximacao e seguido de pausa curta."""
        await self.hover(locator, page)
        await locator.click(timeout=15000)
        await self.pause("curta")

    async def type_text(self, locator, text: str, page=None) -> None:
        """Digitacao caractere a caractere, com ritmo irregular.

        O campo e esvaziado antes: o Chrome preenche formularios sozinho e uma
        tentativa anterior pode ter deixado texto. Digitar por cima concatena os
        dois e o Instagram responde "senha incorreta" com a senha certa.
        """
        await self.hover(locator, page)
        try:
            await locator.click(timeout=10000)
        except Exception:
            pass
        try:
            await locator.fill("")
        except Exception:
            pass
        await self.pause("micro")
        for index, char in enumerate(text):
            await locator.type(char, delay=0)
            base = self.rng.gauss(0.11, 0.045)
            # Pausa maior depois de separadores e de vez em quando no meio.
            if char in "@._-" or (index and index % self.rng.randint(6, 12) == 0):
                base += self.rng.uniform(0.12, 0.45)
            await asyncio.sleep(max(0.03, base) * self.pace)
        await self.pause("curta")

    async def scroll(self, page, distance: int = 900, direction: int = 1) -> None:
        """Rolagem em passos desacelerados, com eventual volta atras."""
        remaining = abs(distance)
        while remaining > 0:
            step = min(remaining, self.rng.randint(90, 260))
            try:
                await page.mouse.wheel(0, step * direction)
            except Exception:
                return
            remaining -= step
            await asyncio.sleep(self.rng.uniform(0.05, 0.24) * self.pace)
            # 18% das vezes a pessoa passa do ponto e volta um pouco.
            if self.rng.random() < 0.18:
                await asyncio.sleep(self.rng.uniform(0.2, 0.7) * self.pace)
                try:
                    await page.mouse.wheel(0, -self.rng.randint(40, 130) * direction)
                except Exception:
                    return
                await asyncio.sleep(self.rng.uniform(0.15, 0.5) * self.pace)
        await self.pause("micro")


def build_human(pace_factor: float, seed: Optional[int] = None) -> Human:
    return Human(pace=pace_factor, rng=random.Random(seed))
