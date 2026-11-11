"""Application compagnon : page web épurée (style Apple) servie par l'application PC sur le réseau local.

Le téléphone (même Wi-Fi) ouvre l'adresse donnée par le QR code des Réglages ; la page peut être
ajoutée à l'écran d'accueil et se comporte alors comme une application. Les données restent sur le
réseau local : aucun serveur extérieur.
"""
from .server import CompanionServer, local_ip

__all__ = ["CompanionServer", "local_ip"]
