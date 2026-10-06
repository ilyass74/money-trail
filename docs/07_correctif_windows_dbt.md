# Correctif du nettoyage des journaux dbt sous Windows

Le journal transmis montre que les assertions métier passent et que le rejet
de surallocation fonctionne. La suite échoue ensuite en supprimant son dossier
temporaire : WinError 32 sur `invalid/logs/dbt.log`. Le build final Money Trail
n'a donc pas encore été exécuté par ce lancement.

Le lanceur appelle désormais dbt dans un processus Python séparé et attend sa
terminaison. Les fichiers ouverts par dbt ne restent plus détenus par le processus
de test lors du nettoyage. Les secrets sont transmis dans l'environnement du
processus enfant, pas dans les arguments de commande.

Appliquer ce correctif dans le dossier existant, puis relancer :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_business.ps1
```

Ne pas relancer l'import ni supprimer le volume PostgreSQL. La validation reste
la réussite du test Python, suivie du build final et de `REFERENCE_RESULTS_OK`.

Sources : journal d'exécution fourni ; Python, subprocess.run :
https://docs.python.org/3/library/subprocess.html
