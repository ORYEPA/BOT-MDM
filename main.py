import os
import asyncio
import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv("TOKEN")
RIOT_API_KEY  = os.getenv("RIOT_API_KEY")

if not DISCORD_TOKEN or not RIOT_API_KEY:
    raise RuntimeError("Faltan TOKEN o RIOT_API_KEY en .env")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------- Utilidades Riot ----------
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

async def riot_get(session, url, params=None):
    """GET con backoff simple en 429 (Rate Limit)."""
    for attempt in range(5):
        async with session.get(url, headers=HEADERS, params=params) as r:
            if r.status == 429:
                retry = int(r.headers.get("Retry-After", "1"))
                await asyncio.sleep(retry + 0.5)
                continue
            if r.status == 404:
                return None
            r.raise_for_status()
            return await r.json()
    raise RuntimeError("Exceso de reintentos (rate limit)")

def split_riot_id(riot_id: str):
    """Ej: 'GameName#TAG' -> ('GameName','TAG')."""
    if "#" not in riot_id:
        raise ValueError("Usa formato RiotID: Nombre#TAG")
    return riot_id.split("#", 1)

# ---------- Slash: TFT Rank ----------
@tree.command(name="tft_rank", description="Muestra el rango de un jugador en TFT")
@app_commands.describe(riot_id="Formato: Nombre#TAG", region="Servidor (p.ej. la1, la2, na1, euw1). Default la1")
async def tft_rank(interaction: discord.Interaction, riot_id: str, region: str = "la1"):
    await interaction.response.defer()
    gameName, tagLine = split_riot_id(riot_id)

    # 1) PUUID vía ACCOUNT-V1 (usa cluster AMERICAS/EUROPE/ASIA)
    account_url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}"
    async with aiohttp.ClientSession() as session:
        account = await riot_get(session, account_url)
        if not account:
            await interaction.followup.send("No encontré ese RiotID.")
            return
        puuid = account["puuid"]

        # 2) Summoner en TFT (usa routing de plataforma p.ej. la1)
        summ_url = f"https://{region}.api.riotgames.com/tft/summoner/v1/summoners/by-puuid/{puuid}"
        summ = await riot_get(session, summ_url)
        if not summ:
            await interaction.followup.send("Sin datos de TFT para ese jugador/servidor.")
            return

        # 3) Entradas de liga (puede haber múltiples colas)
        league_url = f"https://{region}.api.riotgames.com/tft/league/v1/entries/by-summoner/{summ['id']}"
        leagues = await riot_get(session, league_url) or []
        entry = next((e for e in leagues if e.get("queueType") == "RANKED_TFT"), None)

        if not entry:
            await interaction.followup.send(f"{riot_id} no tiene rango en clasificatoria TFT en {region}.")
            return

        tier = entry["tier"].title()
        div  = entry["rank"]
        lp   = entry["leaguePoints"]
        await interaction.followup.send(f"**{riot_id}** → {tier} {div} ({lp} LP) en {region}")

# ---------- Slash: VALORANT Leaderboard ----------
@tree.command(name="valorant_leaderboard", description="Top del leaderboard competitivo por Act (VAL-RANKED-V1)")
@app_commands.describe(act_id="Act ID (usa VAL-CONTENT-V1)", shard="Shard: na | eu | ap | kr | br | latam | pbe", top="Cuántos mostrar (1-20)")
async def valorant_leaderboard(interaction: discord.Interaction, act_id: str, shard: str = "latam", top: int = 5):
    await interaction.response.defer()
    top = max(1, min(top, 20))
    # Leaderboard es público por Act (no es 'rank por jugador' fuera del top).
    # https://developer.riotgames.com/api-details/val-ranked-v1
    url = f"https://{shard}.api.riotgames.com/val/ranked/v1/leaderboards/by-act/{act_id}"
    params = {"size": top}
    async with aiohttp.ClientSession() as session:
        data = await riot_get(session, url, params=params)
        if not data or not data.get("players"):
            await interaction.followup.send("No pude obtener el leaderboard.")
            return
        lines = [f"**Top {top} {shard.upper()}** (Act {act_id[:8]}…):"]
        for i, p in enumerate(data["players"][:top], 1):
            name = (p.get("gameName") or "Desconocido")
            tag  = (p.get("tagLine") or "")
            rr   = p.get("rankedRating", 0)
            tier = p.get("competitiveTier", "?")
            lines.append(f"{i}. {name}#{tag} — Tier {tier} • RR {rr}")
        await interaction.followup.send("\n".join(lines))

# ---------- Slash: VALORANT HS% (última partida, si tienes acceso) ----------
@tree.command(name="valorant_hs", description="HS% aprox. de la última partida del jugador (requiere acceso a VAL-MATCH-V1)")
@app_commands.describe(riot_id="Formato: Nombre#TAG", cluster="Cluster: americas | europe | asia (para endpoints de VAL)")
async def valorant_hs(interaction: discord.Interaction, riot_id: str, cluster: str = "americas"):
    await interaction.response.defer()
    gameName, tagLine = split_riot_id(riot_id)

    async with aiohttp.ClientSession() as session:
        # PUUID (ACCOUNT-V1 en cluster)
        account_url = f"https://{cluster}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}"
        account = await riot_get(session, account_url)
        if not account:
            await interaction.followup.send("No encontré ese RiotID.")
            return
        puuid = account["puuid"]

        # Matchlist por PUUID
        matchlist_url = f"https://{cluster}.api.riotgames.com/val/match/v1/matchlists/by-puuid/{puuid}"
        matchlist = await riot_get(session, matchlist_url)
        if not matchlist or not matchlist.get("history"):
            await interaction.followup.send("No hay historial disponible (puede requerir RSO/producción).")
            return

        last_id = matchlist["history"][0]["matchId"]
        match_url = f"https://{cluster}.api.riotgames.com/val/match/v1/matches/{last_id}"
        match = await riot_get(session, match_url)
        if not match:
            await interaction.followup.send("No pude leer la última partida (permisos).")
            return

        # Buscar al participante y estimar HS%
        player = next((p for p in match["players"] if p.get("puuid") == puuid), None)
        if not player:
            await interaction.followup.send("No hallé stats del jugador en la partida.")
            return

        stats = player.get("stats") or {}
        hs = stats.get("headshots")
        bs = stats.get("bodyshots")
        ls = stats.get("legshots")
        if hs is None or bs is None or ls is None:
            await interaction.followup.send("El detalle de tiros (head/body/leg) no está disponible en esta partida.")
            return

        total_hits = hs + bs + ls
        hs_pct = (hs / total_hits * 100) if total_hits else 0.0
        await interaction.followup.send(f"**{riot_id}** — HS% última partida: **{hs_pct:.2f}%** (H:{hs} B:{bs} L:{ls})")

# ---------- Arranque ----------
@client.event
async def on_ready():
    await tree.sync()
    print(f"Conectado como {client.user} (ID: {client.user.id})")

client.run(DISCORD_TOKEN)
