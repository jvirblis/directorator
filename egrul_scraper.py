#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import random
import traceback
import argparse
import csv
import re
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class InfiniteIter:
    """Itérateur infini pour numéroter les lignes."""
    def __iter__(self):
        self.num = 1
        return self

    def __next__(self):
        num = self.num
        self.num += 1
        return num


def pause(min_sec=2.0, add_sec=5.0):
    """Pause l'exécution pour un temps aléatoire entre 2 et 7 secondes."""
    time.sleep(random.uniform(min_sec, min_sec + add_sec))


def create_driver(chrome_options, chromedriver_path=None):
    """Crée une nouvelle instance du driver Chrome."""
    try:
        if chromedriver_path:
            service = Service(executable_path=chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
        
        driver.set_page_load_timeout(120)
        driver.implicitly_wait(1)
        return driver
    except Exception as e:
        print(f"Erreur lors de la création du driver: {str(e)}")
        return None


def ensure_driver_alive(driver, chrome_options, chromedriver_path=None):
    """Vérifie si le driver est toujours actif, sinon le recrée."""
    try:
        driver.current_url
        return driver
    except Exception as e:
        print(f"Driver inactif détecté: {str(e)}")
        print("Création d'un nouveau driver...")
        try:
            driver.quit()
        except:
            pass
        
        new_driver = create_driver(chrome_options, chromedriver_path)
        if new_driver:
            try:
                new_driver.get("https://egrul.nalog.ru/index.html")
                pause(min_sec=1.0, add_sec=2.0)
            except Exception as e:
                print(f"Erreur lors du chargement de la page: {str(e)}")
        return new_driver


def is_individual_entrepreneur(res_text):
    """
    Vérifie si le résultat concerne un entrepreneur individuel (ИП).
    
    Args:
        res_text: Le texte HTML du div.res-text
        
    Returns:
        bool: True si c'est un ИП (contient ОГРНИП), False sinon
    """
    return 'ОГРНИП' in res_text


def extract_result_data(res_text):
    """
    Extrait les données structurées d'un div.res-text pour les personnes morales.
    
    Args:
        res_text: Le texte HTML du div.res-text
        
    Returns:
        dict avec les champs: full_text, region, ogrn, inn, head_name, status, stop_date
        ou None si c'est un entrepreneur individuel
    """
    # Vérifier si c'est un entrepreneur individuel
    if is_individual_entrepreneur(res_text):
        return None
    
    result = {
        'full_text': res_text,
        'region': '',
        'ogrn': '',
        'inn': '',
        'head_name': '',
        'status': '',
        'stop_date': ''
    }
    
    # Extraire la région (tout avant la première virgule)
    region_match = re.search(r'^([^,]+),', res_text)
    if region_match:
        result['region'] = region_match.group(1).strip()
    
    # Extraire l'OGRN (pas ОГРНИП)
    ogrn_match = re.search(r'ОГРН:\s*(\d+)', res_text)
    if ogrn_match:
        result['ogrn'] = ogrn_match.group(1)
    
    # Extraire l'INN
    inn_match = re.search(r'ИНН:\s*(\d+)', res_text)
    if inn_match:
        result['inn'] = inn_match.group(1)
    
    # Extraire le nom du dirigeant (chercher plusieurs variantes de titres)
    # Les titres possibles après КПП
    head_patterns = [
        r'ГЕНЕРАЛЬНЫЙ ДИРЕКТОР:\s*(.+?)(?:,\s*Дата|$)',
        r'ДИРЕКТОР:\s*(.+?)(?:,\s*Дата|$)',
        r'руководитель юридического лица:\s*(.+?)(?:,\s*Дата|$)',
        r'руководитель:\s*(.+?)(?:,\s*Дата|$)',
        r'глава:\s*(.+?)(?:,\s*Дата|$)',
        r'иное должностное лицо:\s*(.+?)(?:,\s*Дата|$)',
        r'КПП:\s*\d+,\s*([^:]+?):\s*(.+?)(?:,\s*Дата|$)'
    ]
    
    head_name_candidate = ''
    for pattern in head_patterns:
        head_match = re.search(pattern, res_text, re.IGNORECASE)
        if head_match:
            # Si c'est le dernier pattern (celui avec КПП), on prend le groupe 2
            if 'КПП' in pattern:
                head_name_candidate = head_match.group(2).strip()
            else:
                head_name_candidate = head_match.group(1).strip()
            break
    
    # Valider que head_name ne contient pas de chiffres (dates, etc.)
    # On accepte seulement si c'est un nom (lettres, espaces, tirets)
    if head_name_candidate and not re.search(r'\d', head_name_candidate):
        result['head_name'] = head_name_candidate
    
    # Vérifier le statut (liquidé si "Дата прекращения деятельности" est présent)
    if 'Дата прекращения деятельности' in res_text:
        result['status'] = 'liquidated'
        
        # Extraire la date de cessation
        stop_date_match = re.search(r'Дата прекращения деятельности:\s*(\d{2}\.\d{2}\.\d{4})', res_text)
        if stop_date_match:
            result['stop_date'] = stop_date_match.group(1)
    
    return result


def get_total_pages(driver):
    """
    Détermine le nombre total de pages de résultats disponibles.
    
    Returns:
        int: Nombre de pages (minimum 1)
    """
    try:
        # Chercher tous les liens de pagination
        page_links = driver.find_elements(By.CLASS_NAME, "lnk-page")
        if not page_links:
            return 1
        
        # Trouver le numéro de page le plus élevé
        max_page = 1
        for link in page_links:
            try:
                page_num = int(link.get_attribute("data-page"))
                if page_num > max_page:
                    max_page = page_num
            except (ValueError, TypeError):
                continue
        
        return max_page
    except Exception as e:
        print(f"Erreur lors de la détection du nombre de pages: {str(e)}")
        return 1


def go_to_page(driver, page_number, min_sec=2.0, max_retries=3):
    """
    Navigue vers une page spécifique de résultats.
    
    Args:
        driver: Le driver Selenium
        page_number: Numéro de la page à atteindre
        min_sec: Temps de pause minimum
        max_retries: Nombre de tentatives en cas d'élément obsolète
        
    Returns:
        bool: True si la navigation a réussi, False sinon
    """
    for attempt in range(max_retries):
        try:
            # Re-chercher le lien de pagination à chaque tentative (évite les références obsolètes)
            page_link = driver.find_element(By.CSS_SELECTOR, f'a.lnk-page[data-page="{page_number}"]')
            page_link.click()
            pause(min_sec=min_sec, add_sec=2.0)
            return True
            
        except StaleElementReferenceException:
            if attempt < max_retries - 1:
                print(f"Élément obsolète détecté, nouvelle tentative {attempt + 2}/{max_retries}")
                pause(min_sec=1.0, add_sec=1.0)
                continue
            else:
                print(f"Impossible d'accéder à la page {page_number} après {max_retries} tentatives (élément obsolète)")
                return False
                
        except NoSuchElementException:
            print(f"Lien de pagination pour la page {page_number} non trouvé")
            return False
            
        except Exception as e:
            print(f"Erreur lors de la navigation vers la page {page_number}: {str(e)}")
            return False
    
    return False


def get_new_pdf_name(storage_path, done_files):
    """Identifie le nouveau fichier PDF téléchargé."""
    new_done_files = os.listdir(storage_path)
    new_files = list(set(new_done_files) - set(done_files))

    if len(new_files) == 1:
        return new_files[0]
    return None


def check_unfinished_download(storage_path):
    """Vérifie s'il y a des téléchargements en cours."""
    return [
        file_name for file_name in os.listdir(storage_path) if file_name.endswith(".crdownload")
    ]


def manage_unfinished_download(storage_path):
    """Gère les téléchargements inachevés."""
    unfinished_download_files = check_unfinished_download(storage_path)

    if unfinished_download_files:
        pause(min_sec=10.0, add_sec=10.0)

    unfinished_download_files = check_unfinished_download(storage_path)

    if unfinished_download_files:
        for udf in unfinished_download_files:
            udf_path = os.path.join(storage_path, udf)

            if os.path.exists(udf_path):
                os.remove(udf_path)
            
        return True
    
    return False


def wait_for_overlays_to_disappear(driver, timeout=10):
    """
    Attend que les overlays de blocage disparaissent.
    
    Args:
        driver: Le driver Selenium
        timeout: Temps maximum d'attente en secondes
    """
    try:
        # Attendre que les blockUI overlays disparaissent
        WebDriverWait(driver, timeout).until(
            lambda d: len(d.find_elements(By.CLASS_NAME, "blockUI")) == 0
        )
    except Exception as e:
        # Si le timeout est atteint, continuer quand même
        print(f"Avertissement: overlay toujours présent après {timeout}s")


def download_pdf_for_entity(driver, result_elem, storage_path, entity_name, inn, min_sec=1.0):
    """
    Télécharge le PDF pour une entité donnée.
    
    Args:
        driver: Le driver Selenium
        result_elem: L'élément res-row contenant le résultat
        storage_path: Chemin du dossier de stockage des PDFs
        entity_name: Nom de l'entité (non utilisé dans le nouveau format)
        inn: INN de l'entité pour nommer le fichier
        min_sec: Temps de pause minimum
        
    Returns:
        str: Nom du fichier téléchargé ou None si échec
    """
    try:
        # Liste des fichiers avant téléchargement
        done_files = os.listdir(storage_path)
        
        # Attendre que les overlays de blocage disparaissent
        wait_for_overlays_to_disappear(driver, timeout=10)
        
        # Trouver le bouton de téléchargement
        button = result_elem.find_element(By.TAG_NAME, "button")
        
        # Essayer de cliquer normalement
        try:
            button.click()
        except ElementClickInterceptedException:
            # Si le clic normal échoue, utiliser JavaScript comme alternative
            print(f"Clic normal bloqué pour INN {inn}, utilisation de JavaScript")
            driver.execute_script("arguments[0].click();", button)
        
        pause(min_sec=min_sec, add_sec=2.0)
        
        # Gérer les téléchargements inachevés
        manage_unfinished_download(storage_path)
        
        # Identifier le nouveau PDF téléchargé
        new_pdf_name = get_new_pdf_name(storage_path, done_files)
        if new_pdf_name:
            # Créer un nom de fichier avec INN et date: INN_YYYYMMDD.pdf
            download_date = time.strftime("%Y%m%d")
            new_filename = f"{inn}_{download_date}.pdf"
            new_path = os.path.join(storage_path, new_filename)
            
            # Vérifier si le fichier existe déjà, ajouter un timestamp si nécessaire
            if os.path.exists(new_path):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                new_filename = f"{inn}_{timestamp}.pdf"
                new_path = os.path.join(storage_path, new_filename)
            
            os.rename(os.path.join(storage_path, new_pdf_name), new_path)
            return new_filename
        else:
            print(f"Aucun nouveau fichier PDF détecté pour INN: {inn}")
            return None
            
    except Exception as e:
        print(f"Erreur lors du téléchargement du PDF pour INN {inn}: {str(e)}")
        return None


def search_and_extract_results(driver, search_query, max_records=500, storage_path=None, download_pdfs=False, min_sec=2.0, max_retries=2):
    """
    Recherche et extrait toutes les données des résultats avec pagination.
    
    Args:
        max_records: Nombre maximum d'enregistrements à collecter par requête
        storage_path: Chemin pour stocker les PDFs (requis si download_pdfs=True)
        download_pdfs: Si True, télécharge les PDFs pour les entités non liquidées
    
    Returns:
        tuple: (list de dict pour personnes morales, list de dict pour entrepreneurs individuels)
               ou (None, None) en cas d'erreur
    """
    retries = 0
    while retries <= max_retries:
        try:
            search = driver.find_element(By.ID, "query")
            search.clear()
            search.send_keys(search_query)
            search_button = driver.find_element(By.ID, "btnSearch")
            search_button.click()
            pause(min_sec=min_sec, add_sec=3.0)

            # Listes pour accumuler tous les résultats de toutes les pages
            all_legal_entities = []
            all_entrepreneurs = []
            total_records = 0
            
            # Déterminer le nombre total de pages
            total_pages = get_total_pages(driver)
            print(f"Nombre de pages détectées pour '{search_query}': {total_pages}")
            
            # Parcourir toutes les pages
            for page_num in range(1, total_pages + 1):
                # Si on a déjà atteint la limite, arrêter
                if total_records >= max_records:
                    print(f"Limite de {max_records} enregistrements atteinte pour '{search_query}'")
                    break
                
                # Pour la page 1, on est déjà dessus après la recherche
                # Pour les autres pages, naviguer
                if page_num > 1:
                    success = go_to_page(driver, page_num, min_sec=min_sec)
                    if not success:
                        print(f"Impossible d'accéder à la page {page_num}, arrêt de la pagination")
                        break
                
                print(f"Extraction de la page {page_num}/{total_pages} pour '{search_query}'")
                
                # Récupérer tous les résultats de cette page
                all_results = driver.find_elements(By.CLASS_NAME, "res-row")
                if not all_results:
                    print(f"Aucun résultat trouvé sur la page {page_num}")
                    break
                
                # Extraire les données de chaque résultat sur cette page
                page_legal_entities = []
                page_entrepreneurs = []
                
                for result_elem in all_results:
                    # Vérifier si on a atteint la limite
                    if total_records >= max_records:
                        break
                    
                    try:
                        # Extraire le nom de l'entité depuis res-caption
                        entity_name = ''
                        try:
                            res_caption = result_elem.find_element(By.CLASS_NAME, "res-caption")
                            link_elem = res_caption.find_element(By.TAG_NAME, "a")
                            # Extraire le texte entre <a> et </a>
                            entity_name = link_elem.text.strip()
                        except Exception as e:
                            print(f"Impossible d'extraire le nom de l'entité: {str(e)}")
                        
                        # Chercher le div.res-text dans ce résultat
                        res_text_elem = result_elem.find_element(By.CLASS_NAME, "res-text")
                        res_text = res_text_elem.text
                        
                        # Vérifier si c'est un entrepreneur individuel
                        if is_individual_entrepreneur(res_text):
                            # Stocker seulement le texte complet pour les ИП
                            page_entrepreneurs.append({
                                'search_query': search_query,
                                'entity_name': entity_name,
                                'full_text': res_text
                            })
                        else:
                            # Extraire les données structurées pour les personnes morales
                            extracted_data = extract_result_data(res_text)
                            if extracted_data:  # Devrait toujours être non-None ici
                                extracted_data['search_query'] = search_query
                                extracted_data['entity_name'] = entity_name
                                
                                # Télécharger le PDF si demandé et si l'entité n'est pas liquidée
                                pdf_filename = ''
                                if download_pdfs and storage_path:
                                    if extracted_data['status'] != 'liquidated':
                                        pdf_filename = download_pdf_for_entity(
                                            driver, 
                                            result_elem, 
                                            storage_path, 
                                            entity_name, 
                                            extracted_data['inn']
                                        )
                                        if pdf_filename:
                                            print(f"PDF téléchargé: {pdf_filename}")
                                
                                extracted_data['pdf_file'] = pdf_filename
                                page_legal_entities.append(extracted_data)
                        
                        total_records += 1
                        
                    except Exception as e:
                        print(f"Erreur lors de l'extraction d'un résultat: {str(e)}")
                        continue
                
                # Ajouter les résultats de cette page aux listes globales
                all_legal_entities.extend(page_legal_entities)
                all_entrepreneurs.extend(page_entrepreneurs)
                
                print(f"Page {page_num}: {len(page_legal_entities)} personne(s) morale(s), {len(page_entrepreneurs)} entrepreneur(s) individuel(s)")
            
            print(f"Total pour '{search_query}': {len(all_legal_entities)} personne(s) morale(s) et {len(all_entrepreneurs)} entrepreneur(s) individuel(s) ({total_records} enregistrements)")
            return all_legal_entities, all_entrepreneurs
            
        except NoSuchElementException:
            if retries < max_retries:
                print(f"Éléments introuvables pour: {search_query}, essai {retries+1}/{max_retries+1}")
                try:
                    driver.refresh()
                    pause(min_sec=min_sec, add_sec=3.0)
                except:
                    return None, None
                retries += 1
            else:
                print(f"Éléments introuvables pour: {search_query} après {max_retries+1} tentatives")
                return None, None
                
        except Exception as e:
            print(f"Erreur lors de la recherche pour {search_query}: {str(e)}")
            if "invalid session id" in str(e).lower():
                return None, None
            
            if retries < max_retries:
                print(f"Essai {retries+1}/{max_retries+1}")
                try:
                    driver.refresh()
                    pause(min_sec=min_sec, add_sec=3.0)
                except:
                    return None, None
                retries += 1
            else:
                print(f"Échec après {max_retries+1} tentatives")
                return None, None
    
    return None, None


def read_search_queries(file_path, column_index=0):
    """Lit la liste des requêtes de recherche à partir d'un fichier CSV."""
    queries = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # Détecter le délimiteur automatiquement
        sniffer = csv.Sniffer()
        sample = f.read(1024)
        f.seek(0)
        
        try:
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter
        except:
            # Par défaut, utiliser la virgule
            delimiter = ','
        
        # Si le délimiteur est un point-virgule, l'utiliser
        if ';' in sample and delimiter != ';':
            delimiter = ';'
        
        csv_reader = csv.reader(f, delimiter=delimiter, quotechar='"')
        header = next(csv_reader, None)  # Lire l'en-tête
        
        if header:
            print(f"En-têtes détectés: {header}")
            print(f"Utilisation de la colonne {column_index}: {header[column_index] if column_index < len(header) else 'Index hors limites'}")
        
        for row in csv_reader:
            if row and len(row) > column_index:
                query = row[column_index].strip().replace('"', '')
                if query:
                    queries.append(query)
    
    print(f"Nombre total de requêtes trouvées: {len(queries)}")
    
    # Supprimer les doublons tout en préservant l'ordre
    seen = set()
    return [x for x in queries if not (x in seen or seen.add(x))]


def write_results_to_csv(results, output_file):
    """Écrit les résultats des personnes morales dans un fichier CSV."""
    fieldnames = ['search_query', 'entity_name', 'full_text', 'region', 'ogrn', 'inn', 'head_name', 'status', 'stop_date', 'pdf_file']
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    print(f"Résultats des personnes morales écrits dans: {output_file}")


def write_entrepreneurs_to_csv(entrepreneurs, output_file):
    """Écrit les résultats des entrepreneurs individuels dans un fichier CSV simple."""
    fieldnames = ['search_query', 'entity_name', 'full_text']
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entrepreneurs)
    
    print(f"Résultats des entrepreneurs individuels écrits dans: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Extraire des données structurées d\'EGRUL en utilisant des requêtes de recherche')
    parser.add_argument('--input-file', required=True, help='Chemin vers le fichier CSV contenant les requêtes de recherche')
    parser.add_argument('--output-file', default='egrul_results.csv', help='Fichier CSV de sortie pour les personnes morales')
    parser.add_argument('--entrepreneurs-file', default='egrul_entrepreneurs.csv', help='Fichier CSV de sortie pour les entrepreneurs individuels')
    parser.add_argument('--max-records', type=int, default=500, help='Nombre maximum d\'enregistrements à collecter par requête (défaut: 500)')
    parser.add_argument('--download-pdfs', action='store_true', help='Télécharger les PDFs pour les entités non liquidées')
    parser.add_argument('--pdf-dir', default='pdfs', help='Répertoire de sortie pour les PDF téléchargés (défaut: pdfs)')
    parser.add_argument('--chromedriver-path', default=None, 
                        help='Chemin vers le chromedriver (optionnel avec selenium 4.10+)')
    parser.add_argument('--headless', action='store_true', help='Exécuter Chrome en mode headless')
    parser.add_argument('--column', type=int, default=0, 
                        help='Index de la colonne contenant les requêtes (0 pour la première colonne)')
    args = parser.parse_args()

    # Lire la liste des requêtes
    try:
        queries = read_search_queries(args.input_file, args.column)
        
        if len(queries) == 0:
            print("Aucune requête valide trouvée dans le fichier CSV.")
            return
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier d'entrée: {str(e)}")
        traceback.print_exc()
        return

    # Créer le répertoire de stockage des PDFs s'il est activé
    storage_path = None
    if args.download_pdfs:
        storage_path = os.path.abspath(args.pdf_dir)
        os.makedirs(storage_path, exist_ok=True)
        print(f"Les PDFs seront téléchargés dans: {storage_path}")

    # Configuration des options Chrome
    chrome_options = Options()
    if args.headless:
        chrome_options.add_argument("--headless")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    
    # Configuration des préférences de téléchargement si activé
    if args.download_pdfs and storage_path:
        prefs = {
            "download.default_directory": storage_path,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": False,
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1
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
        pause(min_sec=1.0, add_sec=2.0)
    except Exception as e:
        print(f"Erreur lors de l'ouverture du site: {str(e)}")
        driver.quit()
        return

    all_legal_entities = []
    all_entrepreneurs = []
    success_count = 0
    fail_count = 0

    try:
        for i, query in enumerate(tqdm(queries, desc="Extraction des données")):
            try:
                # Vérifier et éventuellement recréer le driver toutes les 20 tentatives
                if i % 20 == 0 and i > 0:
                    driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                    if not driver:
                        print("Impossible de maintenir le driver actif. Arrêt du processus.")
                        break

                # Rechercher et extraire les résultats
                try:
                    legal_entities, entrepreneurs = search_and_extract_results(
                        driver, query, 
                        max_records=args.max_records, 
                        storage_path=storage_path, 
                        download_pdfs=args.download_pdfs
                    )
                    if legal_entities is None and entrepreneurs is None:
                        # Erreur de session, essayer de récupérer
                        print(f"Échec pour la requête {query}, tentative de récupération du driver...")
                        driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                        if driver:
                            legal_entities, entrepreneurs = search_and_extract_results(
                                driver, query, 
                                max_records=args.max_records, 
                                storage_path=storage_path, 
                                download_pdfs=args.download_pdfs
                            )
                        
                    if legal_entities is None and entrepreneurs is None:
                        fail_count += 1
                        continue
                    
                    # Ajouter les résultats aux listes globales
                    if legal_entities:
                        all_legal_entities.extend(legal_entities)
                    if entrepreneurs:
                        all_entrepreneurs.extend(entrepreneurs)
                    
                    if legal_entities or entrepreneurs:
                        success_count += 1
                    else:
                        fail_count += 1

                except ElementClickInterceptedException:
                    print(f"Élément non cliquable pour la requête: {query}, tentative de récupération...")
                    driver = ensure_driver_alive(driver, chrome_options, args.chromedriver_path)
                    if driver:
                        legal_entities, entrepreneurs = search_and_extract_results(
                            driver, query, 
                            max_records=args.max_records, 
                            storage_path=storage_path, 
                            download_pdfs=args.download_pdfs, 
                            min_sec=2.0
                        )
                        if legal_entities or entrepreneurs:
                            if legal_entities:
                                all_legal_entities.extend(legal_entities)
                            if entrepreneurs:
                                all_entrepreneurs.extend(entrepreneurs)
                            success_count += 1
                        else:
                            fail_count += 1
                    else:
                        fail_count += 1
                        continue

                # Pause entre les recherches
                pause(min_sec=1.0, add_sec=3.0)

            except Exception as ex:
                print(f"Erreur lors du traitement de la requête {query}:")
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
        
        # Écrire les résultats dans les fichiers CSV
        if all_legal_entities:
            write_results_to_csv(all_legal_entities, args.output_file)
        
        if all_entrepreneurs:
            write_entrepreneurs_to_csv(all_entrepreneurs, args.entrepreneurs_file)
        
        print(f"\nRésumé: {success_count} requêtes traitées avec succès, {fail_count} échecs")
        print(f"Total de personnes morales extraites: {len(all_legal_entities)}")
        print(f"Total d'entrepreneurs individuels extraits: {len(all_entrepreneurs)}")


if __name__ == "__main__":
    main()
