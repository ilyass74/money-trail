# Refonte de la présentation client

Cette mise à jour transforme la présentation de Money Trail et clarifie le
parcours métier. Elle s'applique à l'interface existante ; les comptes, sessions,
calculs, sources et dossiers de suivi sont conservés.

## Ce qui change

La page de connexion présente désormais la plateforme avant de demander les
identifiants : problème financier traité, publics concernés, exemple de
rapprochement et parcours en trois étapes. L'exemple LOT001 est explicitement
identifié comme issu de données de démonstration.

Le formulaire est placé dans une carte distincte, avec aide à la connexion et
explication du rôle du compte. L'identifiant n'est plus prérempli : utiliser
le compte existant `ilyass` et le mot de passe choisi lors de l'installation.
Aucun accès, client, certification, gain mesuré ou témoignage n'est inventé.

La nouvelle identité utilise une marque graphique SVG, une palette vert profond,
un fond clair, une hiérarchie typographique et des composants cohérents.
Les styles comportent des adaptations pour les petites largeurs d'écran.
Les écrans métier ont des introductions plus précises ; la vue d'ensemble
met en avant les prochaines investigations, le détail distingue les composantes
du calcul et l'historique devient un fil de décisions lisible. Les états vides
expliquent où poursuivre le travail.

## Appliquer la mise à jour

Arrêter d'abord le serveur actuel avec Ctrl+C dans sa fenêtre PowerShell.
Télécharger le ZIP dans Downloads puis exécuter :

```powershell
Set-Location C:\Users\HP\Documents\money-trail
Expand-Archive -LiteralPath "$HOME\Downloads\money-trail-interface-design-v2.zip" -DestinationPath . -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh_interface.ps1
```

Le script vérifie les tests puis lance l'interface, sans installation de nouvelles
dépendances et sans migration de base. Ouvrir http://127.0.0.1:8501 ; si la
page précédente reste affichée, utiliser Ctrl+F5. Pour revoir la page de connexion,
se déconnecter dans la barre latérale. Garder le compte et son mot de passe actuels.

## Vérifications

- 36 tests Python réussis, dont affichage des montants inconnus, rédaction des
  résumés et échappement des commentaires dans l'historique HTML.
- 8 tests Streamlit de parcours réussis avec des services simulés : connexion,
  cinq écrans, montants, commentaires, rôles, validation et expiration de session.
- Contrôle du contenu de la connexion : introduction, exemple marqué comme
  démonstration, trois étapes et identifiant non prérempli.

La revue visuelle sur le navigateur du PC reste à effectuer, notamment à ses
dimensions réelles. Les tests de parcours ne garantissent pas la disposition
exacte des pixels dans tous les navigateurs. Cette mise à jour n'altère aucune
requête de calcul ou de suivi en base.

## Sources

- Montants de l'exemple : fixtures de référence Money Trail (LOT001).
- Fonctionnement et parcours : code et tests de la plateforme.
- Streamlit AppTest : https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest
