# Barri a Barri

**El trencaclosques de Barcelona.** Encaixa els 73 barris de Barcelona al mapa, districte a districte, i endevina quins són més grans. Fet amb dades obertes.

- **Mapa:** 10 nivells (un per districte) i el repte final amb tota la ciutat.
- **Dades:** quin és més gran? Ordena quatre barris per superfície.

## Jugar

Descarrega'l a itch.io o a la secció *Releases* (Linux, Windows i versió web).

Linux: descomprimeix i executa `./instalar.sh` (o `sudo ./instalar.sh` per a tots els usuaris).

## Executar des del codi

```bash
pip install pygame-ce
python game.py
```

## Compilar

GitHub Actions compila Linux, Windows i la versió web a cada `push` a `main` (artefactes de l'execució). Si poses una etiqueta `v*` (per exemple `v0.1.0`), també crea una *Release* amb els tres zips.

## Crèdits

- Joc: Lluís Ridao — [lluisridao.com](https://lluisridao.com)
- Dades cartogràfiques: Ajuntament de Barcelona / CartoBCN (CC BY 4.0), via [martgnz/bcn-geodata](https://github.com/martgnz/bcn-geodata)
- Tipografia: DejaVu Sans
- Fet amb Python i [pygame-ce](https://pyga.me/)
