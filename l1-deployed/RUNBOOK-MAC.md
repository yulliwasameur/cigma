# Faire tourner le système réel (lot L1) sur ton Mac — mode d'emploi

**Durée** : environ 1 h 30, dont 1 h où la machine travaille seule.
**Ce qu'il faut** : Docker Desktop, 8 Go de mémoire libres, une connexion Internet.

## 1. Préparer Docker Desktop (5 min)

1. Ouvre Docker Desktop.
2. Va dans *Settings → Resources* et règle : **4 CPU**, **8 Go de mémoire**, 40 Go de disque.
3. Clique sur *Apply & restart*, puis attends que la baleine en bas à gauche soit verte.

Pourquoi : Online Boutique lance 11 petits services, plus Istio (le « maillage » qui chiffre leurs échanges). Avec moins de mémoire, des services tombent.

## 2. Installer les outils (10 min)

Dans le Terminal :

```bash
cd ~/"Claude outputs/cigma-l1"
./setup_mac.sh
```

Le script installe, avec Homebrew : kind (Kubernetes dans Docker), kubectl, helm, istioctl, syft (inventaire logiciel), step (petite autorité de certification) et sslyze (scanner TLS). Il écrit les versions dans `docs/VERSIONS-L1-TOOLS.md`.

## 3. Lancer le système (20 min)

```bash
./cluster_up.sh
```

Le script crée un cluster de 3 nœuds, installe Istio en mTLS strict (tout échange interne est chiffré et authentifié), déploie Online Boutique, puis crée la PKI à deux niveaux de la passerelle : une racine RSA-3072, une intermédiaire ECDSA P-256 et un certificat de passerelle RSA-2048.

Vérification : `kubectl get pods -A` doit montrer tous les pods en `Running`.

## 4. Laisser tourner 15 minutes, puis collecter (15 min)

Le générateur de trafic d'Online Boutique simule des clients. Après 15 minutes :

```bash
./collect/collect_all.sh
```

Il récupère six familles de sources dans `out/public/` : Kubernetes, TLS, PKI, CBOM, CI/CD, télémétrie. Il écrit aussi `PUBLIC_MANIFEST.sha256`.

## 5. Me prévenir

Écris-moi « collecte faite ». Le dossier `out/public/` est sur ton Mac, et je le lis directement. Je convertis les sources en observations pour CIGMA, je calcule les prédictions de toutes les méthodes, puis je les scelle. L'empreinte du scellement est publiée **avant** l'annotation.

Ne lance pas `make l1-predict` toi-même : l'adaptateur des sources réelles se termine de mon côté.

## 6. Annotation (2 personnes + 1 arbitre, environ 3 h chacun)

Les annotateurs suivent `annotate/PROTOCOLE-ANNOTATION.md`. Ils ne voient jamais `out/predictions/`.

## 7. Éteindre

```bash
cd ~/"Claude outputs/cigma-l1" && ./cluster_down.sh
```

## Si ça bloque

- Un pod reste en `Pending` : il manque de la mémoire, monte à 10 Go dans Docker.
- `istioctl` refuse : vérifie la version avec `istioctl version`, puis relance `./cluster_up.sh`.
- Copie le message d'erreur dans la conversation : je corrige le script.
