#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import random
import traceback
import argparse
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException


class InfiniteIter:
    def __iter__(self):
        self.num = 1
        return self

    def __next__(self):
        num = self.num
        self.num += 1
        return num


def pause(min_sec=2.0, add_sec=5.0):
    """Random timeout to avoid blocking by the service, work well this timeout at 1500 records required"""
    time.sleep(random.uniform(min_sec, min_sec + add_sec))


def create_driver(chrome_options, chromedriver_path=None):
    try:
        if chromedriver_path:
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
        
        driver.set_page_load_timeout(120)  # Réduire le timeout pour plus de vitesse
        driver.implicitly_wait(1)  # Attente implicite réduite
        return driver
    except Exception as e:
        print(f"Error in creation driver: {str(e)}")
        return None


def ensure_driver_alive(driver, chrome_options, chromedriver_path=None):
    """Check if the driver is still active, if not reactivate"""
    try:
        # Test simple pour vérifier si le driver fonctionne
        driver.current_url
        return driver
    except Exception as e:
        print(f"Inactive driver detected: {str(e)}")
        print("New driver start...")
        try:
            driver.quit()
        except:
            pass
        
        new_driver = create_driver(chrome_options, chromedriver_path)
        if new_driver:
            try:
                new_driver.get("https://egrul.nalog.ru/index.html")
                pause(min_sec=1.0, add_sec=2.0)  # Pause plus courte pour le rechargement
            except Exception as e:
                print(f"Error loading the page: {str(e)}")
        return new_driver


def get_pdf(driver, search_query, min_sec=2.0, max_retries=2):
    """Searcha and download the  PDF."""
    retries = 0
    while retries <= max_retries:
        try:
            search = driver.find_element(By.ID, "query")
            search.clear()
            search.send_keys(search_query)
            search_button = driver.find_element(By.ID, "btnSearch")
            search_button.click()
            pause(min_sec=min_sec, add_sec=2.0)  # short timeout after search

            all_results = driver.find_elements(By.CLASS_NAME, "res-row")
            if not all_results:
                print(f"Nothing found for: {search_query}")
                return False
            
            # Utilise seulement le premier élément de la recherche
            first_result_button = all_results[0].find_element(By.TAG_NAME, "button")
            first_result_button.click()
            pause(min_sec=1.0, add_sec=1.0)  # Short pause after clic
            return True
            
        except NoSuchElementException:
            if retries < max_retries:
                print(f"Elements not found for: {search_query}, try {retries+1}/{max_retries+1}")
                try:
                    driver.refresh()
                    pause(min_sec=min_sec, add_sec=3.0)
                except:
                    # Si refresh échoue, on retourne False pour que main() puisse recréer le driver
                    return False
                retries += 1
            else:
                print(f"Elements not found for: {search_query} after {max_retries+1} try")
                return False
                
        except Exception as e:
            print(f"Error while searching for {search_query}: {str(e)}")
            # Si c'est une erreur de session, on retourne immédiatement False
            if "invalid session id" in str(e).lower():
                return False
            
            if retries < max_retries:
                print(f"Essai {retries+1}/{max_retries+1}")
                try:
                    driver.refresh()
                    pause(min_sec=min_sec, add_sec=3.0)
                except:
                    return False
                retries += 1
            else:
                print(f"Échec après {max_retries+1} tentatives")
                return False
    
    return False


def get_new_pdf_name(storage_path, done_files):
    """Identify newly downloaded PDF."""
    new_done_files = os.listdir(storage_path)
    new_files = list(set(new_done_files) - set(done_files))

    if len(new_files) == 1:
        return new_files[0]
    return None


def check_unfinished_download(storage_path):
    """Check if there is an unfinished download."""
    return [
        file_name for file_name in os.listdir(storage_path) if file_name.endswith(".crdownload")
    ]


def manage_unfinished_download(storage_path):
    """Manage unfinished downloads."""
    unfinished_download_files = check_unfinished_download(storage_path)

    if unfinished_download_files:
        # Short pause for unfinished downloads
        pause(min_sec=10.0, add_sec=10.0)  # 10-20 secondes au lieu de 60

    unfinished_download_files = check_unfinished_download(storage_path)

    if unfinished_download_files:
        for udf in unfinished_download_files:
            udf_path = os.path.join(storage_path, udf)

            if os.path.exists(udf_path):
                os.remove(udf_path)
            
        return True  # Indique qu'il y avait des téléchargements non terminés
    
    return False


def read_inn_list(file_path):
    """Read CSV with INN."""
    import csv
    inn_list = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # Check delimiter
        # todo is an overkill feature, should use standartized CSV and not need if a propper DB 
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(f.read(1024))
        f.seek(0)
        
        # Forcer l'utilisation du point-virgule si détecté ou spécifier explicitement
        if dialect.delimiter == ';':
            delimiter = ';'
        else:
            delimiter = ','
        
        csv_reader = csv.reader(f, delimiter=delimiter, quotechar='"')
        header = next(csv_reader, None)  # Lire l'en-tête
        
        # Déterminer l'index de la colonne INN
        inn_col_index = 0  # Par défaut, utiliser la première colonne
        if header:
            print(f"En-têtes détectés: {header}")
            # Chercher une colonne qui pourrait contenir des INN
            possible_headers = ['inn', 'ИНН', 'inn_number', 'id', 'code']
            for i, col_name in enumerate(header):
                col_name_clean = col_name.strip().replace('"', '').lower()
                if col_name_clean in [h.lower() for h in possible_headers]:
                    inn_col_index = i
                    print(f"Colonne INN détectée à l'index {i}: {col_name}")
                    break
            
            # Si on n'a pas trouvé, vérifier si c'est la 4ème colonne (index 3)
            if inn_col_index == 0 and len(header) > 3:
                if header[3].strip().replace('"', '').lower() == 'инн':
                    inn_col_index = 3
                    print(f"Colonne INN trouvée à l'index 3: {header[3]}")
            
        # Lire les INN de la colonne appropriée
        for row_num, row in enumerate(csv_reader, 1):
            if row and len(row) > inn_col_index:
                inn = row[inn_col_index].strip().replace('"', '')
                # Check if this is at least 10 digits  (format of Russian INN)
                if inn and inn.isdigit() and len(inn) == 10:
                    inn_list.append(inn)
                elif inn:
                    print(f"INN not valid at lign {row_num}: '{inn}' (not only numbers or not correct length)")
    
    print(f"Nombre total d'INN trouvés: {len(inn_list)}")
    
    # Supprimer les doublons tout en préservant l'ordre
    seen = set()
    return [x for x in inn_list if not (x in seen or seen.add(x))]


def main():
    parser = argparse.ArgumentParser(description='Télécharger des PDF en utilisant une liste d\'INN')
    parser.add_argument('--inn-file', required=True, help='Chemin vers le fichier CSV contenant la liste des INN')
    parser.add_argument('--output-dir', default='pdfs', help='Répertoire de sortie pour les PDF téléchargés')
    parser.add_argument('--chromedriver-path', default=None, 
                        help='Chemin vers le chromedriver (optionnel avec selenium 4.10+)')
    parser.add_argument('--headless', action='store_true', help='Exécuter Chrome en mode headless')
    parser.add_argument('--inn-column', type=int, help='Index de la colonne contenant les INN (0 pour la première colonne)')
    args = parser.parse_args()

    # Créer le répertoire de stockage s'il n'existe pas
    storage_path = os.path.abspath(args.output_dir)
    os.makedirs(storage_path, exist_ok=True)
    
    # Lire la liste des INN
    try:
        inn_list = read_inn_list(args.inn_file)
        if args.inn_column is not None:
            print(f"Utilisation de la colonne {args.inn_column} pour les INN")
            # Si l'utilisateur a spécifié une colonne spécifique, on relance la lecture
            def read_specific_column(file_path, column_index):
                import csv
                inn_list = []
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Détecter le délimiteur
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(f.read(1024))
                    f.seek(0)
                    
                    delimiter = ';' if dialect.delimiter == ';' else ','
                    csv_reader = csv.reader(f, delimiter=delimiter, quotechar='"')
                    header = next(csv_reader, None)  # Sauter l'en-tête
                    
                    for row in csv_reader:
                        if row and len(row) > column_index:
                            inn = row[column_index].strip().replace('"', '')
                            if inn and inn.isdigit() and len(inn) >= 10:
                                inn_list.append(inn)
                # Supprimer les doublons
                seen = set()
                return [x for x in inn_list if not (x in seen or seen.add(x))]
            
            inn_list = read_specific_column(args.inn_file, args.inn_column)
        
        print(f"Nombre d'INN à traiter: {len(inn_list)}")
        if len(inn_list) == 0:
            print("Aucun INN valide trouvé dans le fichier CSV.")
            return
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier INN: {str(e)}")
        traceback.print_exc()
        return

    # Configuration des options Chrome (à utiliser pour tous les drivers)
    chrome_options = Options()
    if args.headless:
        chrome_options.add_argument("--headless")
    
    # Ajouter des options pour la stabilité et la vitesse
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-images")  # Désactiver les images pour plus de vitesse
    chrome_options.add_argument("--disable-javascript")  # Désactiver JS non essentiel
    chrome_options.add_argument("--disable-extensions")  # Désactiver les extensions
    
    # Configuration des préférences de téléchargement
    prefs = {
        "download.default_directory": storage_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,
        "profile.default_content_settings.popups": 0,  # Bloquer les pop-ups
        "profile.default_content_setting_values.automatic_downloads": 1  # Autoriser téléchargements
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # Créer le driver initial
    driver = create_driver(chrome_options, args.chromedriver_path)
    if not driver:
        print("Impossible de créer le driver Chrome. Vérifiez votre installation.")
        return

    # Ouvrir le site cible
    try:
        driver.get("https://egrul.nalog.ru/index.html")
        pause(min_sec=1.0, add_sec=2.0)  # Pause réduite au chargement initial
    except Exception as e:
        print(f"Erreur lors de l'ouverture du site: {str(e)}")
        driver.quit()
        return

    success_count = 0
    fail_count = 0
    unfinished_counter = 0

    try:
        for i, inn in enumerate(tqdm(inn_list, desc="Téléchargement des PDF")):
            try:
                # Vérifier et éventuellement recréer le driver toutes les 20 tentatives (au lieu de 10)
                if i % 20 == 0 and i > 0:
                    driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                    if not driver:
                        print("Impossible de maintenir le driver actif. Arrêt du processus.")
                        break

                # Liste des fichiers avant téléchargement
                done_files = os.listdir(storage_path)

                # Essayer de télécharger le PDF
                try:
                    result = get_pdf(driver, inn)
                    if result is False:
                        # Si get_pdf retourne False, cela peut être dû à une session invalide
                        print(f"Échec pour INN {inn}, tentative de récupération du driver...")
                        driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                        if driver:
                            result = get_pdf(driver, inn)
                        
                    if not result:
                        fail_count += 1
                        continue

                except ElementClickInterceptedException:
                    print(f"Élément non cliquable pour INN: {inn}, tentative de récupération...")
                    driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                    if driver:
                        if not get_pdf(driver, inn, min_sec=2.0):  # Pause réduite
                            fail_count += 1
                            continue
                    else:
                        fail_count += 1
                        continue

                # Gérer les téléchargements inachevés
                if manage_unfinished_download(storage_path):
                    unfinished_counter += 1
                    if unfinished_counter > 5:
                        print("ALERTE: Trop de téléchargements inachevés consécutifs")
                        break

                # Identifier le nouveau PDF téléchargé
                new_pdf_name = get_new_pdf_name(storage_path, done_files)
                if new_pdf_name:
                    # Renommer le fichier avec l'INN pour une meilleure organisation
                    new_path = os.path.join(storage_path, f"{inn}_{new_pdf_name}")
                    
                    # Vérifier si le fichier existe déjà pour éviter les écrasements
                    if os.path.exists(new_path):
                        base, ext = os.path.splitext(new_path)
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        new_path = f"{base}_{timestamp}{ext}"
                    
                    os.rename(os.path.join(storage_path, new_pdf_name), new_path)
                    print(f"Fichier téléchargé et renommé: {os.path.basename(new_path)}")
                    success_count += 1
                else:
                    print(f"Aucun nouveau fichier détecté pour INN: {inn}")
                    fail_count += 1

                # Pause plus courte entre les téléchargements
                pause(min_sec=1.0, add_sec=3.0)  # Entre 1 et 4 secondes

            except Exception as ex:
                print(f"Erreur lors du traitement de l'INN {inn}:")
                print(traceback.format_exc())
                
                # Si c'est une erreur de session, essayer de recréer le driver
                if "invalid session id" in str(ex).lower():
                    print("Détection d'une session invalide, création d'un nouveau driver...")
                    driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                    if not driver:
                        print("Impossible de recréer le driver. Arrêt du processus.")
                        break
                
                fail_count += 1

    except KeyboardInterrupt:
        print("\nInterruption par l'utilisateur. Fermeture du navigateur...")
    finally:
        try:
            driver.quit()
        except:
            pass
        print(f"\nRésumé: {success_count} PDF téléchargés avec succès, {fail_count} échecs")


if __name__ == "__main__":
    main()
