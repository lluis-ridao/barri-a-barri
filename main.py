# Punt d'entrada per a la versió web (pygbag). Al web el bucle ha de ser asíncron.
import asyncio

import pygame

import game


async def main():
    g = game.Game()
    while g.running:
        dt = g.clock.tick(game.FPS) / 1000.0
        g.step(pygame.event.get(), dt)
        pygame.display.flip()
        await asyncio.sleep(0)


asyncio.run(main())
