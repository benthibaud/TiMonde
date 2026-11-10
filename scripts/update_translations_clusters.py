#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TiMonde — Mise à jour Massive des Traductions par Grappes (Clusters i18n)
Applique les traductions des 9 nouvelles clés dans l'ensemble des 54 langues.
"""

import os
import sys
import json
import ast
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PO_DIR = os.path.join(ROOT_DIR, "po")

KEYS = [
    "Installed binary:",
    "TiMonde version",
    "[Ephemeral]",
    "Submitted",
    "Edit station",
    "Station deleted:",
    "Open editor to update this station and its country",
    "<small>• Expand folders <b>[▶]</b> to explore subgroups and stations.\n• Use <b>Move Up / Move Down</b> or Drag &amp; Drop to reorder.\n• Use <b>Move to...</b> to organize stations into another folder.</small>",
    "TiMonde uses path conventions with the <b>/</b> separator:\n\n• <b>/</b> or <b>(Root)</b> : Places the station at the root of the menu (without group).\n• <b>/Gabon</b> or <b>Gabon</b> : Places the station in group « Gabon ».\n• <b>/France/Brittany</b> : Places the station in subgroup « Brittany » under « France ».\n• <b>/Belgium/NL</b> : Places the station in subgroup « NL » under « Belgium ».\n• <b>France/Local Radios</b> : Subgroup with spaces under « France ».\n\n<i>Groups and subgroups are automatically created if they do not exist yet.</i>"
]

ALL_CLUSTER_TRANSLATIONS = {
    # -------------------------------------------------------------------------
    # CLUSTER 1 : LANGUES LATINES
    # -------------------------------------------------------------------------
    "pl": {
        KEYS[0]: "Zainstalowany plik binarny:",
        KEYS[1]: "Wersja TiMonde",
        KEYS[2]: "[Tymczasowy]",
        KEYS[3]: "Przesłano",
        KEYS[4]: "Edytuj stację",
        KEYS[5]: "Stacja usunięta:",
        KEYS[6]: "Otwórz edytor, aby zaktualizować tę stację i jej kraj",
        KEYS[7]: "<small>• Rozwiń foldery <b>[▶]</b>, aby przeglądać podgrupy i stacje.\n• Użyj <b>W górę / W dół</b> lub przeciągnij i upuść, aby zmienić kolejność.\n• Użyj <b>Przenieś do...</b>, aby przenieść stacje do innego folderu.</small>",
        KEYS[8]: "TiMonde używa konwencji ścieżek z separatorem <b>/</b>:\n\n• <b>/</b> lub <b>(Katalog główny)</b> : Umieszcza stację w menu głównym (bez grupy).\n• <b>/Gabon</b> lub <b>Gabon</b> : Umieszcza stację w grupie « Gabon ».\n• <b>/Francja/Bretania</b> : Umieszcza stację w podgrupie « Bretania » w « Francja ».\n• <b>/Belgia/NL</b> : Umieszcza stację w podgrupie « NL » w « Belgia ».\n\n<i>Grupy i podgrupy są tworzone automatycznie, jeśli jeszcze nie istnieją.</i>"
    },
    "cs": {
        KEYS[0]: "Nainstalovaný binární soubor:",
        KEYS[1]: "Verze TiMonde",
        KEYS[2]: "[Dočasný]",
        KEYS[3]: "Odesláno",
        KEYS[4]: "Upravit stanici",
        KEYS[5]: "Stanice smazána:",
        KEYS[6]: "Otevřít editor pro aktualizaci této stanice a její země",
        KEYS[7]: "<small>• Rozbalte složky <b>[▶]</b> pro procházení podskupin a stanic.\n• Použijte <b>Nahoru / Dolů</b> nebo přetažení pro změnu pořadí.\n• Použijte <b>Přesunout do...</b> pro uspořádání stanic do jiné složky.</small>",
        KEYS[8]: "TiMonde používá konvence cest s oddělovačem <b>/</b>:\n\n• <b>/</b> nebo <b>(Kořen)</b> : Umístí stanici do kořene nabídky (bez skupiny).\n• <b>/Gabon</b> nebo <b>Gabon</b> : Umístí stanici do skupiny « Gabon ».\n• <b>/Francie/Bretaň</b> : Umístí stanici do podskupiny « Bretaň » pod « Francie ».\n\n<i>Skupiny a podskupiny se vytvoří automaticky, pokud ještě neexistují.</i>"
    },
    "sk": {
        KEYS[0]: "Nainštalovaný binárny súbor:",
        KEYS[1]: "Verzia TiMonde",
        KEYS[2]: "[Dočasný]",
        KEYS[3]: "Odoslané",
        KEYS[4]: "Upraviť stanicu",
        KEYS[5]: "Stanica zmazaná:",
        KEYS[6]: "Otvoriť editor na aktualizáciu tejto stanice a jej krajiny",
        KEYS[7]: "<small>• Rozbaľte priečinky <b>[▶]</b> na preskúmanie podskupín a staníc.\n• Použite <b>Hore / Dole</b> alebo presunutie myšou na zmenu poradia.\n• Použite <b>Presunúť do...</b> na usporiadanie staníc do iného priečinka.</small>",
        KEYS[8]: "TiMonde používa konvencie ciest s oddeľovačom <b>/</b>:\n\n• <b>/</b> alebo <b>(Koreň)</b> : Umiestni stanicu do koreňa ponuky (bez skupiny).\n• <b>/Gabon</b> alebo <b>Gabon</b> : Umiestni stanicu do skupiny « Gabon ».\n• <b>/Francúzsko/Bretónsko</b> : Umiestni stanicu do podskupiny « Bretónsko » pod « Francúzsko ».\n\n<i>Skupiny a podskupiny sa vytvoria automaticky, ak ešte neexistujú.</i>"
    },
    "sl": {
        KEYS[0]: "Nameščena binarna datoteka:",
        KEYS[1]: "Različica TiMonde",
        KEYS[2]: "[Začasno]",
        KEYS[3]: "Poslano",
        KEYS[4]: "Uredi postajo",
        KEYS[5]: "Postaja izbrisana:",
        KEYS[6]: "Odpri urejevalnik za posodobitev te postaje in njene države",
        KEYS[7]: "<small>• Razširite mape <b>[▶]</b> za raziskovanje podskupin in postaj.\n• Uporabite <b>Premakni gor / Premakni dol</b> ali povleci in spusti.\n• Uporabite <b>Premakni v...</b> za premik postaj v drugo mapo.</small>",
        KEYS[8]: "TiMonde uporablja konvencije poti z ločilom <b>/</b>:\n\n• <b>/</b> ali <b>(Koren)</b> : Postavi postajo v koren menija (brez skupine).\n• <b>/Gabon</b> ali <b>Gabon</b> : Postavi postajo v skupino « Gabon ».\n\n<i>Skupine in podskupine se ustvarijo samodejno, če še ne obstajajo.</i>"
    },
    "hr": {
        KEYS[0]: "Instalirana binarna datoteka:",
        KEYS[1]: "Verzija TiMonde",
        KEYS[2]: "[Privremeno]",
        KEYS[3]: "Poslano",
        KEYS[4]: "Uredi postaju",
        KEYS[5]: "Postaja izbrisana:",
        KEYS[6]: "Otvori uređivač za ažuriranje ove postaje i njezine zemlje",
        KEYS[7]: "<small>• Proširite mape <b>[▶]</b> za pregled podgrupa i postaja.\n• Koristite <b>Gore / Dolje</b> ili povlačenje za promjenu redoslijeda.\n• Koristite <b>Premjesti u...</b> za premještanje postaja u drugu mapu.</small>",
        KEYS[8]: "TiMonde koristi konvencije staza s razdjelnikom <b>/</b>:\n\n• <b>/</b> ili <b>(Korijen)</b> : Postavlja postaju u korijen izbornika (bez grupe).\n• <b>/Gabon</b> ili <b>Gabon</b> : Postavlja postaju u grupu « Gabon ».\n\n<i>Grupe i podgrupe stvaraju se automatski ako još ne postoje.</i>"
    },
    "bs": {
        KEYS[0]: "Instalirana binarna datoteka:",
        KEYS[1]: "Verzija TiMonde",
        KEYS[2]: "[Privremeno]",
        KEYS[3]: "Poslano",
        KEYS[4]: "Uredi stanicu",
        KEYS[5]: "Stanica izbrisana:",
        KEYS[6]: "Otvori uređivač za ažuriranje ove stanice i njene zemlje",
        KEYS[7]: "<small>• Proširite foldere <b>[▶]</b> za pregled podgrupa i stanica.\n• Koristite <b>Gore / Dolje</b> ili povlačenje za promjenu redoslijeda.\n• Koristite <b>Premjesti u...</b> za premještanje stanica u drugi folder.</small>",
        KEYS[8]: "TiMonde koristi konvencije putanja s razdjelnikom <b>/</b>:\n\n• <b>/</b> ili <b>(Korijen)</b> : Postavlja stanicu u korijen menija (bez grupe).\n• <b>/Gabon</b> ili <b>Gabon</b> : Postavlja stanicu u grupu « Gabon ».\n\n<i>Grupe i podgrupe se automatski kreiraju ako još ne postoje.</i>"
    },
    "ro": {
        KEYS[0]: "Binar instalat:",
        KEYS[1]: "Versiune TiMonde",
        KEYS[2]: "[Efemer]",
        KEYS[3]: "Trimis",
        KEYS[4]: "Editează postul",
        KEYS[5]: "Post șters:",
        KEYS[6]: "Deschide editorul pentru a actualiza acest post și țara sa",
        KEYS[7]: "<small>• Extinde dosarele <b>[▶]</b> pentru a explora subgrupurile și posturile.\n• Folosește <b>Sus / Jos</b> sau tragere și fixare pentru reordonare.\n• Folosește <b>Mută în...</b> pentru a organiza posturile în alt dosar.</small>",
        KEYS[8]: "TiMonde folosește convenții de cale cu separatorul <b>/</b>:\n\n• <b>/</b> sau <b>(Rădăcină)</b> : Plasează postul în rădăcina meniului (fără grup).\n• <b>/Gabon</b> sau <b>Gabon</b> : Plasează postul în grupul « Gabon ».\n\n<i>Grupurile și subgrupurile sunt create automat dacă nu există deja.</i>"
    },
    "ca": {
        KEYS[0]: "Binari instal·lat:",
        KEYS[1]: "Versió de TiMonde",
        KEYS[2]: "[Efímer]",
        KEYS[3]: "Enviat",
        KEYS[4]: "Edita l'emissora",
        KEYS[5]: "Emissora suprimida:",
        KEYS[6]: "Obre l'editor per actualitzar aquesta emissora i el seu país",
        KEYS[7]: "<small>• Desplegueu carpetes <b>[▶]</b> per explorar subgrups i emissores.\n• Utilitzeu <b>Puja / Baixa</b> o arrossegar i deixar anar per reordenar.\n• Utilitzeu <b>Mou a...</b> per organitzar emissores en una altra carpeta.</small>",
        KEYS[8]: "TiMonde utilitza convencions de camí amb el separador <b>/</b>:\n\n• <b>/</b> o <b>(Arrel)</b> : Col·loca l'emissora a l'arrel del menú (sense grup).\n• <b>/Gabon</b> o <b>Gabon</b> : Col·loca l'emissora al grup « Gabon ».\n\n<i>Els grups i subgrups es creen automàticament si encara no existeixen.</i>"
    },
    "sq": {
        KEYS[0]: "Binar i instaluar:",
        KEYS[1]: "Versioni i TiMonde",
        KEYS[2]: "[E përkohshme]",
        KEYS[3]: "Dërguar",
        KEYS[4]: "Ndrysho stacionin",
        KEYS[5]: "Stacioni u fshi:",
        KEYS[6]: "Hap redaktuesin për të përditësuar këtë stacion dhe shtetin e tij",
        KEYS[7]: "<small>• Zgjero dosjet <b>[▶]</b> për të eksploruar nëngrupet dhe stacionet.\n• Përdor <b>Lart / Poshtë</b> ose tërhiq dhe lësho për të rirenditur.\n• Përdor <b>Zhvendos te...</b> për të organizuar stacionet në një dosje tjetër.</small>",
        KEYS[8]: "TiMonde përdor rregullat e shtegut me ndarësin <b>/</b>:\n\n• <b>/</b> ose <b>(Rrënja)</b> : Vendos stacionin në rrënjën e menysë (pa grup).\n• <b>/Gabon</b> ose <b>Gabon</b> : Vendos stacionin në grupin « Gabon ».\n\n<i>Grupet dhe nëngrupet krijohen automatikisht nëse nuk ekzistojnë ende.</i>"
    },
    "tr": {
        KEYS[0]: "Yüklü ikili dosya:",
        KEYS[1]: "TiMonde sürümü",
        KEYS[2]: "[Geçici]",
        KEYS[3]: "Gönderildi",
        KEYS[4]: "İstasyonu düzenle",
        KEYS[5]: "İstasyon silindi:",
        KEYS[6]: "Bu istasyonu ve ülkesini güncellemek için düzenleyiciyi aç",
        KEYS[7]: "<small>• Alt grupları ve istasyonları keşfetmek için klasörleri <b>[▶]</b> genişletin.\n• Yeniden sıralamak için <b>Yukarı / Aşağı</b> veya Sürükle ve Bırak'\''ı kullanın.\n• İstasyonları başka bir klasöre taşımak için <b>Şuraya taşı...</b>'\''yı kullanın.</small>",
        KEYS[8]: "TiMonde, <b>/</b> ayırıcısı ile yol kurallarını kullanır:\n\n• <b>/</b> veya <b>(Kök)</b> : İstasyonu menünün köküne yerleştirir (grup olmadan).\n• <b>/Gabon</b> veya <b>Gabon</b> : İstasyonu « Gabon » grubuna yerleştirir.\n\n<i>Gruplar ve alt gruplar henüz mevcut değilse otomatik olarak oluşturulur.</i>"
    },
    "id": {
        KEYS[0]: "Biner terpasang:",
        KEYS[1]: "Versi TiMonde",
        KEYS[2]: "[Sementara]",
        KEYS[3]: "Dikirim",
        KEYS[4]: "Edit stasiun",
        KEYS[5]: "Stasiun dihapus:",
        KEYS[6]: "Buka editor untuk memperbarui stasiun ini dan negaranya",
        KEYS[7]: "<small>• Perluas folder <b>[▶]</b> untuk menjelajahi subgrup dan stasiun.\n• Gunakan <b>Naik / Turun</b> atau seret dan lepas untuk menyusun ulang.\n• Gunakan <b>Pindahkan ke...</b> untuk mengatur stasiun ke folder lain.</small>",
        KEYS[8]: "TiMonde menggunakan konvensi jalur dengan pemisah <b>/</b>:\n\n• <b>/</b> atau <b>(Root)</b> : Menempatkan stasiun di root menu (tanpa grup).\n• <b>/Gabon</b> atau <b>Gabon</b> : Menempatkan stasiun di grup « Gabon ».\n\n<i>Grup dan subgrup dibuat secara otomatis jika belum ada.</i>"
    },
    "ms": {
        KEYS[0]: "Binari dipasang:",
        KEYS[1]: "Versi TiMonde",
        KEYS[2]: "[Sementara]",
        KEYS[3]: "Dihantar",
        KEYS[4]: "Edit stesen",
        KEYS[5]: "Stesen dipadamkan:",
        KEYS[6]: "Buka editor untuk mengemas kini stesen ini dan negaranya",
        KEYS[7]: "<small>• Kembangkan folder <b>[▶]</b> untuk meneroka subkumpulan dan stesen.\n• Gunakan <b>Naik / Turun</b> atau seret dan lepas untuk menyusun semula.\n• Gunakan <b>Pindah ke...</b> untuk menyusun stesen ke folder lain.</small>",
        KEYS[8]: "TiMonde menggunakan konvensyen laluan dengan pemisah <b>/</b>:\n\n• <b>/</b> atau <b>(Root)</b> : Meletakkan stesen pada menu utama (tanpa kumpulan).\n• <b>/Gabon</b> atau <b>Gabon</b> : Meletakkan stesen dalam kumpulan « Gabon ».\n\n<i>Kumpulan dan subkumpulan dicipta secara automatik jika belum wujud.</i>"
    },
    "vi": {
        KEYS[0]: "Tập tin nhị phân đã cài đặt:",
        KEYS[1]: "Phiên bản TiMonde",
        KEYS[2]: "[Tạm thời]",
        KEYS[3]: "Đã gửi",
        KEYS[4]: "Chỉnh sửa đài",
        KEYS[5]: "Đài đã bị xóa:",
        KEYS[6]: "Mở trình chỉnh sửa để cập nhật đài này và quốc gia của đài",
        KEYS[7]: "<small>• Mở rộng thư mục <b>[▶]</b> để khám phá nhóm phụ và đài.\n• Dùng <b>Di chuyển lên / Di chuyển xuống</b> hoặc Kéo & Thả để sắp xếp lại.\n• Dùng <b>Di chuyển đến...</b> để sắp xếp các đài vào thư mục khác.</small>",
        KEYS[8]: "TiMonde sử dụng quy ước đường dẫn với dấu phân cách <b>/</b>:\n\n• <b>/</b> hoặc <b>(Gốc)</b> : Đặt đài ở gốc của menu (không có nhóm).\n• <b>/Gabon</b> hoặc <b>Gabon</b> : Đặt đài trong nhóm « Gabon ».\n\n<i>Các nhóm và nhóm phụ sẽ được tạo tự động nếu chưa tồn tại.</i>"
    },
    "da": {
        KEYS[0]: "Installeret binær fil:",
        KEYS[1]: "TiMonde-version",
        KEYS[2]: "[Midlertidig]",
        KEYS[3]: "Indsendt",
        KEYS[4]: "Rediger station",
        KEYS[5]: "Station slettet:",
        KEYS[6]: "Åbn editor for at opdatere denne station og dens land",
        KEYS[7]: "<small>• Udvid mapper <b>[▶]</b> for at udforske undergrupper og stationer.\n• Brug <b>Flyt op / Flyt ned</b> eller træk og slip for at omarrangere.\n• Brug <b>Flyt til...</b> for at organisere stationer i en anden mappe.</small>",
        KEYS[8]: "TiMonde bruger stikonventioner med separatoren <b>/</b>:\n\n• <b>/</b> eller <b>(Rod)</b> : Placerer stationen i menuens rod (uden gruppe).\n• <b>/Gabon</b> eller <b>Gabon</b> : Placerer stationen i gruppen « Gabon ».\n\n<i>Grupper og undergrupper oprettes automatisk, hvis de ikke findes endnu.</i>"
    },
    "nb": {
        KEYS[0]: "Installert binærfil:",
        KEYS[1]: "TiMonde-versjon",
        KEYS[2]: "[Midlertidig]",
        KEYS[3]: "Sendt inn",
        KEYS[4]: "Rediger stasjon",
        KEYS[5]: "Stasjon slettet:",
        KEYS[6]: "Åpne redigeringsprogrammet for å oppdatere denne stasjonen og landet dens",
        KEYS[7]: "<small>• Utvid mapper <b>[▶]</b> for å utforske undergrupper og stasjoner.\n• Bruk <b>Flytt opp / Flytt ned</b> eller dra og slipp for å endre rekkefølge.\n• Bruk <b>Flytt til...</b> for å organisere stasjoner i en annen mappe.</small>",
        KEYS[8]: "TiMonde bruker banekonvensjoner med separatoren <b>/</b>:\n\n• <b>/</b> eller <b>(Rot)</b> : Plasserer stasjonen i roten av menyen (uten gruppe).\n• <b>/Gabon</b> eller <b>Gabon</b> : Plasserer stasjonen i gruppen « Gabon ».\n\n<i>Grupper og undergrupper opprettes automatisk hvis de ikke finnes ennå.</i>"
    },
    "sv": {
        KEYS[0]: "Installerad binärfil:",
        KEYS[1]: "TiMonde-version",
        KEYS[2]: "[Tillfällig]",
        KEYS[3]: "Skickad",
        KEYS[4]: "Redigera station",
        KEYS[5]: "Station raderad:",
        KEYS[6]: "Öppna redigeraren för att uppdatera denna station och dess land",
        KEYS[7]: "<small>• Expandera mappar <b>[▶]</b> för att utforska undergrupper och stationer.\n• Använd <b>Flytta upp / Flytta ned</b> eller dra och släpp för att ordna om.\n• Använd <b>Flytta till...</b> för att organisera stationer i en annan mapp.</small>",
        KEYS[8]: "TiMonde använder sökvägskonventioner med avgränsaren <b>/</b>:\n\n• <b>/</b> eller <b>(Rot)</b> : Placerar stationen i menyns rot (utan grupp).\n• <b>/Gabon</b> eller <b>Gabon</b> : Placerar stationen i gruppen « Gabon ».\n\n<i>Grupper och undergrupper skapas automatiskt om de inte redan finns.</i>"
    },
    "fi": {
        KEYS[0]: "Asennettu binaaritiedosto:",
        KEYS[1]: "TiMonde-versio",
        KEYS[2]: "[Väliaikainen]",
        KEYS[3]: "Lähetetty",
        KEYS[4]: "Muokkaa asemaa",
        KEYS[5]: "Asema poistettu:",
        KEYS[6]: "Avaa muokkain päivittääksesi tämän aseman ja sen maan",
        KEYS[7]: "<small>• Laajenna kansioita <b>[▶]</b> tutkiaksesi alaryhmiä ja asemia.\n• Käytä <b>Siirrä ylös / Siirrä alas</b> tai vedä ja pudota järjestääksesi.\n• Käytä <b>Siirrä kohteeseen...</b> järjestääksesi asemat toiseen kansioon.</small>",
        KEYS[8]: "TiMonde käyttää polkukäytäntöjä erottimella <b>/</b>:\n\n• <b>/</b> tai <b>(Juuri)</b> : Asettaa aseman valikon juureen (ilman ryhmää).\n• <b>/Gabon</b> tai <b>Gabon</b> : Asettaa aseman ryhmään « Gabon ».\n\n<i>Ryhmät ja alaryhmät luodaan automaattisesti, jos niitä ei vielä ole.</i>"
    },
    "et": {
        KEYS[0]: "Paigaldatud binaarfail:",
        KEYS[1]: "TiMonde versioon",
        KEYS[2]: "[Ajutine]",
        KEYS[3]: "Saadetud",
        KEYS[4]: "Muuda jaama",
        KEYS[5]: "Jaam kustutatud:",
        KEYS[6]: "Ava redaktor jaama ja selle riigi uuendamiseks",
        KEYS[7]: "<small>• Ava kaustad <b>[▶]</b> alamgruppide ja jaamade uurimiseks.\n• Kasuta <b>Liiguta üles / Liiguta alla</b> või lohista ümberjärjestamiseks.\n• Kasuta <b>Liiguta asukohta...</b> jaamade teise kausta korraldamiseks.</small>",
        KEYS[8]: "TiMonde kasutab teekonventsioone eraldajaga <b>/</b>:\n\n• <b>/</b> või <b>(Juur)</b> : Paigutab jaama menüü juurde (ilma grupita).\n• <b>/Gabon</b> või <b>Gabon</b> : Paigutab jaama gruppi « Gabon ».\n\n<i>Grupid ja alamgrupid luuakse automaatselt, kui neid veel pole.</i>"
    },
    "lv": {
        KEYS[0]: "Instalētais binārais fails:",
        KEYS[1]: "TiMonde versija",
        KEYS[2]: "[Pagaidu]",
        KEYS[3]: "Iesniegts",
        KEYS[4]: "Rediģēt staciju",
        KEYS[5]: "Stacija dzēsta:",
        KEYS[6]: "Atvērt redaktoru, lai atjauninātu šo staciju un tās valsti",
        KEYS[7]: "<small>• Izvērsiet mapes <b>[▶]</b>, lai izpētītu apakšgrupas un stacijas.\n• Izmantojiet <b>Pārvietot augšup / lejup</b> vai vilkšanu, lai pārkārtotu.\n• Izmantojiet <b>Pārvietot uz...</b>, lai kārtotu stacijas citā mapē.</small>",
        KEYS[8]: "TiMonde izmanto ceļu konvencijas ar atdalītāju <b>/</b>:\n\n• <b>/</b> vai <b>(Sakne)</b> : Novieto staciju izvēlnes saknē (bez grupas).\n• <b>/Gabona</b> vai <b>Gabona</b> : Novieto staciju grupā « Gabona ».\n\n<i>Grupas un apakšgrupas tiek izveidotas automātiski, ja tās vēl nepastāv.</i>"
    },
    "lt": {
        KEYS[0]: "Įdiegta dvejetainė byla:",
        KEYS[1]: "TiMonde versija",
        KEYS[2]: "[Laikinas]",
        KEYS[3]: "Pateikta",
        KEYS[4]: "Redaguoti stotį",
        KEYS[5]: "Stotis ištrinta:",
        KEYS[6]: "Atidaryti redaktorių, norint atnaujinti šią stotį ir jos šalį",
        KEYS[7]: "<small>• Išskleiskite aplankus <b>[▶]</b>, kad naršytumėte pogrupius ir stotis.\n• Naudokite <b>Aukštyn / Žemyn</b> arba tempkite ir numeskite.\n• Naudokite <b>Perkelti į...</b>, kad tvarkytumėte stotis kitame aplanke.</small>",
        KEYS[8]: "TiMonde naudoja kelių taisykles su skyrikliu <b>/</b>:\n\n• <b>/</b> arba <b>(Šaknis)</b> : Įdeda stotį į meniu šaknį (be grupės).\n• <b>/Gabonas</b> arba <b>Gabonas</b> : Įdeda stotį į grupę « Gabonas ».\n\n<i>Grupės ir pogrupiai sukuriami automatiškai, jei jų dar nėra.</i>"
    },
    "hu": {
        KEYS[0]: "Telepített bináris:",
        KEYS[1]: "TiMonde verzió",
        KEYS[2]: "[Ideiglenes]",
        KEYS[3]: "Beküldve",
        KEYS[4]: "Állomás szerkesztése",
        KEYS[5]: "Állomás törölve:",
        KEYS[6]: "Szerkesztő megnyitása az állomás és országa frissítéséhez",
        KEYS[7]: "<small>• Mappák <b>[▶]</b> kibontása az alcsoportok és állomások felfedezéséhez.\n• <b>Mozgatás fel / le</b> vagy fogd és vidd az átrendezéshez.\n• <b>Áthelyezés...</b> az állomások másik mappába rendezéséhez.</small>",
        KEYS[8]: "A TiMonde a <b>/</b> elválasztóval ellátott elérési út konvenciókat használja:\n\n• <b>/</b> vagy <b>(Gyökér)</b> : Az állomást a menü gyökerébe helyezi (csoport nélkül).\n• <b>/Gabon</b> vagy <b>Gabon</b> : Az állomást a « Gabon » csoportba helyezi.\n\n<i>A csoportok és alcsoportok automatikusan létrejönnek, ha még nem léteznek.</i>"
    },
    "is": {
        KEYS[0]: "Uppsett tvíundarskrá:",
        KEYS[1]: "TiMonde útgáfa",
        KEYS[2]: "[Tímabundið]",
        KEYS[3]: "Sent inn",
        KEYS[4]: "Breyta stöð",
        KEYS[5]: "Stöð eytt:",
        KEYS[6]: "Opna ritil til að uppfæra þessa stöð og land hennar",
        KEYS[7]: "<small>• Stækka möppur <b>[▶]</b> til að skoða undirhópa og stöðvar.\n• Notaðu <b>Færa upp / Færa niður</b> eða draga og sleppa til að endurraða.\n• Notaðu <b>Færa í...</b> til að skipuleggja stöðvar í aðra möppu.</small>",
        KEYS[8]: "TiMonde notar slóðareglur með <b>/</b> skiptitákninu:\n\n• <b>/</b> eða <b>(Rót)</b> : Setur stöðina í rót valmyndarinnar (án hóps).\n• <b>/Gabon</b> eða <b>Gabon</b> : Setur stöðina í hópinn « Gabon ».\n\n<i>Hópar og undirhópar eru búnir til sjálfkrafa ef þeir eru ekki þegar til.</i>"
    },
    "az": {
        KEYS[0]: "Quraşdırılmış ikili fayl:",
        KEYS[1]: "TiMonde versiyası",
        KEYS[2]: "[Müvəqqəti]",
        KEYS[3]: "Göndərildi",
        KEYS[4]: "Stansiyanı redaktə et",
        KEYS[5]: "Stansiya silindi:",
        KEYS[6]: "Bu stansiyanı və ölkəsini yeniləmək üçün redaktoru açın",
        KEYS[7]: "<small>• Alt qrupları və stansiyaları görmək üçün qovluqları <b>[▶]</b> açın.\n• Sıralamaq üçün <b>Yuxarı / Aşağı</b> və ya Sürüklə-Burax istifadə edin.\n• Stansiyaları başqa qovluğa köçürmək üçün <b>Köçür...</b> istifadə edin.</small>",
        KEYS[8]: "TiMonde <b>/</b> ayırıcısı olan yol qaydalarından istifadə edir:\n\n• <b>/</b> və ya <b>(Kök)</b> : Stansiyanı menyunun kökünə yerləşdirir (qrup olmadan).\n• <b>/Qabon</b> və ya <b>Qabon</b> : Stansiyanı « Qabon » qrupuna yerləşdirir.\n\n<i>Qruplar və alt qruplar mövcud olmadıqda avtomatik yaradılır.</i>"
    },
    "uz": {
        KEYS[0]: "O'rnatilgan binar fayl:",
        KEYS[1]: "TiMonde versiyasi",
        KEYS[2]: "[Vaqtinchalik]",
        KEYS[3]: "Yuborildi",
        KEYS[4]: "Stansiyani tahrirlash",
        KEYS[5]: "Stansiya o'chirildi:",
        KEYS[6]: "Ushbu stansiya va uning mamlakatini yangilash uchun tahrirlovchini oching",
        KEYS[7]: "<small>• Quyi guruhlar va stansiyalarni ko'rish uchun jildlarni <b>[▶]</b> kengaytiring.\n• Tartibni o'zgartirish uchun <b>Yuqoriga / Pastga</b> yoki sudrab olib tashlashdan foydalaning.\n• Stansiyalarni boshqa jildga ko'chirish uchun <b>Ko'chirish...</b> dan foydalaning.</small>",
        KEYS[8]: "TiMonde <b>/</b> ajratuvchisi bilan yo'l qoidalaridan foydalanadi:\n\n• <b>/</b> yoki <b>(Ildiz)</b> : Stansiyani menyu ildiziga joylashtiradi (guruhsiz).\n• <b>/Gabon</b> yoki <b>Gabon</b> : Stansiyani « Gabon » guruhiga joylashtiradi.\n\n<i>Guruhlar va quyi guruhlar mavjud bo'lmasa, avtomatik yaratiladi.</i>"
    },

    # -------------------------------------------------------------------------
    # CLUSTER 2 : LANGUES CYRILLIQUES
    # -------------------------------------------------------------------------
    "bg": {
        KEYS[0]: "Инсталиран бинарен файл:",
        KEYS[1]: "Версия на TiMonde",
        KEYS[2]: "[Временна]",
        KEYS[3]: "Изпратено",
        KEYS[4]: "Редактиране на станция",
        KEYS[5]: "Станцията е изтрита:",
        KEYS[6]: "Отворете редактора за актуализиране на тази станция и нейната държава",
        KEYS[7]: "<small>• Разгънете папките <b>[▶]</b> за преглед на подгрупи и станции.\n• Използвайте <b>Нагоре / Надолу</b> или плъзгане за пренареждане.\n• Използвайте <b>Преместване в...</b> за подреждане на станции в друга папка.</small>",
        KEYS[8]: "TiMonde използва конвенции за пътища с разделител <b>/</b>:\n\n• <b>/</b> или <b>(Корен)</b> : Поставя станцията в корена на менюто (без група).\n• <b>/Габон</b> или <b>Габон</b> : Поставя станцията в група « Габон ».\n\n<i>Групите и подгрупите се създават автоматично, ако все още не съществуват.</i>"
    },
    "sr": {
        KEYS[0]: "Инсталирани бинарни фајл:",
        KEYS[1]: "Верзија TiMonde",
        KEYS[2]: "[Привремено]",
        KEYS[3]: "Послато",
        KEYS[4]: "Уреди станицу",
        KEYS[5]: "Станица избрисана:",
        KEYS[6]: "Отворите уређивач да бисте ажурирали ову станицу и њену земљу",
        KEYS[7]: "<small>• Раширите фасцикле <b>[▶]</b> да истражите подгрупе и станице.\n• Користите <b>Горе / Доле</b> или превлачење за промену редоследа.\n• Користите <b>Премести у...</b> да организујете станице у другу фасциклу.</small>",
        KEYS[8]: "TiMonde користи конвенције путање са разделником <b>/</b>:\n\n• <b>/</b> или <b>(Корен)</b> : Поставља станицу у корен менија (без групе).\n• <b>/Габон</b> или <b>Габон</b> : Поставља станицу у групу « Габон ».\n\n<i>Групе и подгрупе се аутоматски креирају ако још увек не постоје.</i>"
    },
    "mk": {
        KEYS[0]: "Инсталирана бинарна датотека:",
        KEYS[1]: "Верзија на TiMonde",
        KEYS[2]: "[Привремено]",
        KEYS[3]: "Испратено",
        KEYS[4]: "Уреди станица",
        KEYS[5]: "Станицата е избришана:",
        KEYS[6]: "Отворете уредувач за ажурирање на оваа станица и нејзината земја",
        KEYS[7]: "<small>• Проширете ги папките <b>[▶]</b> за преглед на подгрупи и станици.\n• Користете <b>Горе / Долу</b> или влечење за преуредување.\n• Користете <b>Премести во...</b> за организирање станици во друга папка.</small>",
        KEYS[8]: "TiMonde користи правила за патека со сепаратор <b>/</b>:\n\n• <b>/</b> или <b>(Корен)</b> : Ја става станицата во коренот на менито (без група).\n• <b>/Габон</b> или <b>Габон</b> : Ја става станицата во група « Габон ».\n\n<i>Групите и подгрупите се создаваат автоматски ако сè уште не постојат.</i>"
    },
    "kk": {
        KEYS[0]: "Орнатылған бинарлық файл:",
        KEYS[1]: "TiMonde нұсқасы",
        KEYS[2]: "[Уақытша]",
        KEYS[3]: "Жіберілді",
        KEYS[4]: "Станцияны өңдеу",
        KEYS[5]: "Станция жойылды:",
        KEYS[6]: "Осы станция мен оның елін жаңарту үшін редакторды ашыңыз",
        KEYS[7]: "<small>• Ішкі топтар мен станцияларды көру үшін қалталарды <b>[▶]</b> ашыңыз.\n• Реттеу үшін <b>Жоғары / Төмен</b> немесе сүйреп апаруды пайдаланыңыз.\n• Станцияларды басқа қалтаға көшіру үшін <b>Көшіру...</b> пайдаланыңыз.</small>",
        KEYS[8]: "TiMonde <b>/</b> бөлгіші бар жол ережелерін пайдаланады:\n\n• <b>/</b> немесе <b>(Түбір)</b> : Станцияны мәзірдің түбіріне орналастырады (топсыз).\n• <b>/Габон</b> немесе <b>Габон</b> : Станцияны « Габон » тобына орналастырады.\n\n<i>Топтар мен ішкі топтар әлі жоқ болса, автоматты түрде жасалады.</i>"
    },
    "ky": {
        KEYS[0]: "Орнотулган бинардык файл:",
        KEYS[1]: "TiMonde версиясы",
        KEYS[2]: "[Убактылуу]",
        KEYS[3]: "Жөнөтүлдү",
        KEYS[4]: "Станцияны түзөтүү",
        KEYS[5]: "Станция өчүрүлдү:",
        KEYS[6]: "Бул станцияны жана анын өлкөсүн жаңыртуу үчүн редакторду ачыңыз",
        KEYS[7]: "<small>• Ички топторду жана станцияларды көрүү үчүн папкаларды <b>[▶]</b> ачыңыз.\n• Иреттөө үчүн <b>Өйдө / Төмөн</b> же сүйрөп коюуну колдонуңуз.\n• Станцияларды башка папкага жылдыруу үчүн <b>Жылдыруу...</b> колдонуңуз.</small>",
        KEYS[8]: "TiMonde <b>/</b> бөлгүчү бар жол эрежелерин колдонот:\n\n• <b>/</b> же <b>(Тамыр)</b> : Станцияны менюнун тамырына жайгаштырат (топсуз).\n• <b>/Габон</b> же <b>Габон</b> : Станцияны « Габон » тобуна жайгаштырат.\n\n<i>Топтор жана ички топтор жок болсо, автоматтык түрдө түзүлөт.</i>"
    },
    "mn": {
        KEYS[0]: "Суулгасан хоёртын файл:",
        KEYS[1]: "TiMonde хувилбар",
        KEYS[2]: "[Түр зуурын]",
        KEYS[3]: "Илгээсэн",
        KEYS[4]: "Станц засах",
        KEYS[5]: "Станц устгагдсан:",
        KEYS[6]: "Энэ станц болон улсыг шинэчлэхийн тулд засварлагчийг нээнэ үү",
        KEYS[7]: "<small>• Дэд бүлгүүд болон станцуудыг харахын тулд хавтаснуудыг <b>[▶]</b> дэлгэнэ үү.\n• Дарааллыг өөрчлөхийн тулд <b>Дээш / Доош</b> эсвэл чирж тавина уу.\n• Өөр хавтас руу зөөхийн тулд <b>Зөөх...</b> сонголтыг ашиглана уу.</small>",
        KEYS[8]: "TiMonde нь <b>/</b> тусгаарлагч бүхий замын дүрмийг ашигладаг:\n\n• <b>/</b> эсвэл <b>(Үндэс)</b> : Станцыг цэсийн үндсэнд байрлуулна (бүлэггүй).\n• <b>/Габон</b> эсвэл <b>Габон</b> : Станцыг « Габон » бүлэгт байрлуулна.\n\n<i>Бүлэг байхгүй бол автоматаар үүсгэгдэнэ.</i>"
    },
    "tg": {
        KEYS[0]: "Файли дуӣ насбшуда:",
        KEYS[1]: "Версияи TiMonde",
        KEYS[2]: "[Муваққатӣ]",
        KEYS[3]: "Фиристода шуд",
        KEYS[4]: "Таҳрири радио",
        KEYS[5]: "Радио нест карда шуд:",
        KEYS[6]: "Барои навсозии ин радио ва кишвари он муҳаррирро кушоед",
        KEYS[7]: "<small>• Барои дидани зергурӯҳҳо ва радиоҳо ҷузвдонҳоро <b>[▶]</b> кушоед.\n• Барои тартиб додан <b>Боло / Поён</b> ё кашида партофтанро истифода баред.\n• Барои кӯчонидани радиоҳо ба ҷузвдони дигар <b>Кӯчонидан ба...</b> истифода баред.</small>",
        KEYS[8]: "TiMonde қоидаҳои роҳро бо ҷудокунандаи <b>/</b> истифода мебарад:\n\n• <b>/</b> ё <b>(Реша)</b> : Радиоро дар решаи меню ҷойгир мекунад (бе гурӯҳ).\n• <b>/Габон</b> ё <b>Габон</b> : Радиоро ба гурӯҳи « Габон » мегузорад.\n\n<i>Гурӯҳҳо ва зергурӯҳҳо ба таври худкор эҷод карда мешаванд.</i>"
    },

    # -------------------------------------------------------------------------
    # CLUSTER 3 : CJK RESTANT (ko)
    # -------------------------------------------------------------------------
    "ko": {
        KEYS[0]: "설치된 바이너리:",
        KEYS[1]: "TiMonde 버전",
        KEYS[2]: "[임시 탐색]",
        KEYS[3]: "제출됨",
        KEYS[4]: "방송국 편집",
        KEYS[5]: "방송국 삭제됨:",
        KEYS[6]: "이 방송국과 해당 국가를 업데이트하려면 편집기를 여세요",
        KEYS[7]: "<small>• 폴더 <b>[▶]</b>를 확장하여 하위 그룹과 방송국을 탐색합니다.\n• <b>위로 / 아래로</b> 또는 드래그 앤 드롭으로 순서를 변경합니다.\n• <b>이동...</b>을 사용하여 방송국을 다른 폴더로 정리합니다.</small>",
        KEYS[8]: "TiMonde는 <b>/</b> 구분 기호가 있는 경로 규칙을 사용합니다:\n\n• <b>/</b> 또는 <b>(루트)</b> : 방송국을 메뉴 루트에 배치합니다 (그룹 없음).\n• <b>/가봉</b> 또는 <b>가봉</b> : 방송국을 « 가봉 » 그룹에 배치합니다.\n• <b>/프랑스/브르타뉴</b> : « 프랑스 » 아래의 « 브르타뉴 » 하위 그룹에 배치합니다.\n\n<i>그룹 및 하위 그룹이 아직 없는 경우 자동으로 생성됩니다.</i>"
    },

    # -------------------------------------------------------------------------
    # CLUSTER 4 : SÉMITIQUE RESTANT (he)
    # -------------------------------------------------------------------------
    "he": {
        KEYS[0]: "קובץ הפעלה מותקן:",
        KEYS[1]: "גרסת TiMonde",
        KEYS[2]: "[זמני]",
        KEYS[3]: "נשלח",
        KEYS[4]: "ערוך תחנה",
        KEYS[5]: "התחנה נמחקה:",
        KEYS[6]: "פתח עורך כדי לעדכן תחנה זו ואת המדינה שלה",
        KEYS[7]: "<small>• הרחב תיקיות <b>[▶]</b> כדי לחקור תת-קבוצות ותחנות.\n• השתמש ב-<b>הזז למעלה / הזז למטה</b> או גרור ושחרר לסדר מחדש.\n• השתמש ב-<b>העבר אל...</b> לארגון תחנות בתיקייה אחרת.</small>",
        KEYS[8]: "TiMonde משתמש במוסכמות נתיב עם המפריד <b>/</b>:\n\n• <b>/</b> או <b>(שורש)</b> : מציב את התחנה בשורש התפריט (ללא קבוצה).\n• <b>/גבון</b> או <b>גבון</b> : מציב את התחנה בקבוצה « גבון ».\n\n<i>קבוצות ותת-קבוצות נוצרות באופן אוטומטי אם אינן קיימות עדיין.</i>"
    },

    # -------------------------------------------------------------------------
    # CLUSTER 5 : SUD-ASIATIQUES, CAUCASIENNES & SPÉCIFIQUES
    # -------------------------------------------------------------------------
    "el": {
        KEYS[0]: "Εγκατεστημένο εκτελέσιμο:",
        KEYS[1]: "Έκδοση TiMonde",
        KEYS[2]: "[Εφήμερο]",
        KEYS[3]: "Υποβλήθηκε",
        KEYS[4]: "Επεξεργασία σταθμού",
        KEYS[5]: "Ο σταθμός διαγράφηκε:",
        KEYS[6]: "Άνοιγμα επεξεργαστή για ενημέρωση αυτού του σταθμού και της χώρας του",
        KEYS[7]: "<small>• Αναπτύξτε φακέλους <b>[▶]</b> για εξερεύνηση υποομάδων και σταθμών.\n• Χρησιμοποιήστε <b>Μετακίνηση πάνω / κάτω</b> ή σύρετε για αναδιάταξη.\n• Χρησιμοποιήστε <b>Μετακίνηση σε...</b> για οργάνωση σε άλλο φάκελο.</small>",
        KEYS[8]: "Το TiMonde χρησιμοποιεί συμβάσεις διαδρομής με διαχωριστικό <b>/</b>:\n\n• <b>/</b> ή <b>(Ρίζα)</b> : Τοποθετεί τον σταθμό στη ρίζα του μενού (χωρίς ομάδα).\n• <b>/Γκαμπόν</b> ή <b>Γκαμπόн</b> : Τοποθετεί τον σταθμό στην ομάδα « Γκαμπόν ».\n\n<i>Οι ομάδες δημιουργούνται αυτόματα εάν δεν υπάρχουν ήδη.</i>"
    },
    "hy": {
        KEYS[0]: "Տեղադրված երկուական ֆայլ.",
        KEYS[1]: "TiMonde տարբերակ",
        KEYS[2]: "[Ժամանակավոր]",
        KEYS[3]: "Ուղարկված է",
        KEYS[4]: "Խմբագրել կայանը",
        KEYS[5]: "Կայանը ջնջված է.",
        KEYS[6]: "Բացել խմբագրիչը՝ այս կայանը և նրա երկիրը թարմացնելու համար",
        KEYS[7]: "<small>• Բացեք պանակները <b>[▶]</b>՝ ենթախմբերն ու կայանները ուսումնասիրելու համար:\n• Օգտագործեք <b>Վեր / Վար</b> կամ քաշեք և թողեք՝ վերադասավորելու համար:\n• Օգտագործեք <b>Տեղափոխել...</b>՝ կայանները այլ պանակում կազմակերպելու համար:</small>",
        KEYS[8]: "TiMonde-ն օգտագործում է ուղու կանոններ <b>/</b> բաժանարարով:\n\n• <b>/</b> կամ <b>(Արմատ)</b> : Կայանը տեղադրում է մենյուի արմատում (առանց խմբի):\n• <b>/Գաբոն</b> կամ <b>Գաբոն</b> : Տեղադրում է կայանը « Գաբոն » խմբում:\n\n<i>Խմբերը ստեղծվում են ինքնաբերաբար, եթե դեռ գոյություն չունեն:</i>"
    },
    "ka": {
        KEYS[0]: "დაინსტალირებული ბინარული ფაილი:",
        KEYS[1]: "TiMonde ვერსია",
        KEYS[2]: "[დროებითი]",
        KEYS[3]: "გაგზავნილია",
        KEYS[4]: "სადგურის რედაქტირება",
        KEYS[5]: "სადგური წაიშალა:",
        KEYS[6]: "გახსენით რედაქტორი ამ სადგურისა და მისი ქვეყნის განსაახლებლად",
        KEYS[7]: "<small>• გააფართოვეთ საქაღალდეები <b>[▶]</b> ქვეჯგუფებისა და სადგურების სანახავად.\n• გამოიყენეთ <b>ზემოთ / ქვემოთ</b> ან გადაათრიეთ გადასაადგილებლად.\n• გამოიყენეთ <b>გადატანა...</b> სადგურების სხვა საქაღალდეში გადასატანად.</small>",
        KEYS[8]: "TiMonde იყენებს გზის წესებს <b>/</b> გამყოფით:\n\n• <b>/</b> ან <b>(ძირი)</b> : ათავსებს სადგურს მენიუს ძირში (ჯგუფის გარეშე).\n• <b>/გაბონი</b> ან <b>გაბონი</b> : ათავსებს სადგურს « გაბონი » ჯგუფში.\n\n<i>ჯგუფები ავტომატურად იქმნება, თუ ისინი ჯერ არ არსებობს.</i>"
    },
    "th": {
        KEYS[0]: "ไฟล์ไบนารีที่ติดตั้ง:",
        KEYS[1]: "เวอร์ชัน TiMonde",
        KEYS[2]: "[ชั่วคราว]",
        KEYS[3]: "ส่งแล้ว",
        KEYS[4]: "แก้ไขสถานี",
        KEYS[5]: "ลบสถานีแล้ว:",
        KEYS[6]: "เปิดตัวแก้ไขเพื่ออัปเดตสถานีนี้และประเทศ",
        KEYS[7]: "<small>• ขยายโฟลเดอร์ <b>[▶]</b> เพื่อสำรวจกลุ่มย่อยและสถานี\n• ใช้ <b>เลื่อนขึ้น / เลื่อนลง</b> หรือลากและวางเพื่อจัดลำดับใหม่\n• ใช้ <b>ย้ายไปที่...</b> เพื่อจัดระเบียบสถานีไปยังโฟลเดอร์อื่น</small>",
        KEYS[8]: "TiMonde ใช้รูปแบบเส้นทางที่มีตัวคั่น <b>/</b>:\n\n• <b>/</b> หรือ <b>(รูท)</b> : วางสถานีไว้ที่รูทของเมนู (ไม่มีกลุ่ม)\n• <b>/กาบอง</b> หรือ <b>กาบอง</b> : วางสถานีในกลุ่ม « กาบอง »\n\n<i>กลุ่มและกลุ่มย่อยจะถูกสร้างขึ้นโดยอัตโนมัติหากยังไม่มีอยู่</i>"
    },
    "lo": {
        KEYS[0]: "ໄຟລ໌ຖານສອງທີ່ຕິດຕັ້ງ:",
        KEYS[1]: "ລຸ້ນ TiMonde",
        KEYS[2]: "[ຊົ່ວຄາວ]",
        KEYS[3]: "ສົ່ງແລ້ວ",
        KEYS[4]: "ແກ້ໄຂສະຖານີ",
        KEYS[5]: "ລຶບສະຖານີແລ້ວ:",
        KEYS[6]: "ເປີດຕົວແກ້ໄຂເພື່ອອັບເດດສະຖານີນີ້ແລະປະເທດ",
        KEYS[7]: "<small>• ຂະຫຍາຍໂຟນເດີ <b>[▶]</b> ເພື່ອສຳຫຼວດກຸ່ມຍ່ອຍ ແລະ ສະຖານີ.\n• ໃຊ້ <b>ຍ້າຍຂຶ້ນ / ຍ້າຍລົງ</b> ຫຼື ລາກແລະວາງ ເພື່ອຈັດລຳດັບໃໝ່.\n• ໃຊ້ <b>ຍ້າຍໄປທີ່...</b> ເພື່ອຈັດລະບຽບສະຖານີໄປໃສ່ໂຟນເດີອື່ນ.</small>",
        KEYS[8]: "TiMonde ໃຊ້ສົນທິສັນຍາເສັ້ນທາງທີ່ມີຕົວຂັ້ນ <b>/</b>:\n\n• <b>/</b> ຫຼື <b>(ຮາກ)</b> : ວາງສະຖານີໄວ້ທີ່ຮາກຂອງເມນູ (ບໍ່ມີກຸ່ມ).\n• <b>/ກາບອງ</b> ຫຼື <b>ກາບອງ</b> : ວາງສະຖານີໃນກຸ່ມ « ກາບອງ ».\n\n<i>ກຸ່ມຈະຖືກສ້າງຂຶ້ນໂດຍອັດຕະໂນມັດຖ້າພວກມັນຍັງບໍ່ທັນມີ.</i>"
    },
    "km": {
        KEYS[0]: "ឯកសារគោលពីរដែលបានដំឡើង៖",
        KEYS[1]: "កំណែ TiMonde",
        KEYS[2]: "[បណ្ដោះអាសន្ន]",
        KEYS[3]: "បានដាក់ស្នើ",
        KEYS[4]: "កែសម្រួលស្ថានីយ",
        KEYS[5]: "ស្ថានីយត្រូវបានលុប៖",
        KEYS[6]: "បើកកម្មវិធីកែសម្រួលដើម្បីធ្វើបច្ចុប្បន្នភាពស្ថានីយនេះនិងប្រទេសរបស់វា",
        KEYS[7]: "<small>• ពង្រីកថត <b>[▶]</b> ដើម្បីរុករកក្រុមរងនិងស្ថានីយ។\n• ប្រើ <b>ផ្លាស់ទីឡើង / ចុះ</b> ឬអូសទម្លាក់ដើម្បីរៀបចំឡើងវិញ។\n• ប្រើ <b>ផ្លាស់ទីទៅ...</b> ដើម្បីរៀបចំស្ថានីយទៅក្នុងថតផ្សេងទៀត។</small>",
        KEYS[8]: "TiMonde ប្រើអនុសញ្ញាផ្លូវជាមួយសញ្ញាបំបែក <b>/</b>៖\n\n• <b>/</b> ឬ <b>(Root)</b> ៖ ដាក់ស្ថានីយនៅឫសនៃម៉ឺនុយ (ដោយគ្មានក្រុម)។\n• <b>/ហ្គាបុង</b> ឬ <b>ហ្គាបុង</b> ៖ ដាក់ស្ថានីយនៅក្នុងក្រុម « ហ្គាបុង »។\n\n<i>ក្រុមនិងក្រុមរងត្រូវបានបង្កើតដោយស្វ័យប្រវត្តិប្រសិនបើវាមិនទាន់មាន។</i>"
    },
    "my": {
        KEYS[0]: "ထည့်သွင်းထားသော ဘာsecondary ဖိုင်-",
        KEYS[1]: "TiMonde ဗားရှင်း",
        KEYS[2]: "[ယာယီ]",
        KEYS[3]: "တင်ပြပြီး",
        KEYS[4]: "ရေဒီယိုလိုင်းကို ပြင်ဆင်ရန်",
        KEYS[5]: "လိုင်းကို ဖျက်ပြီးပါပြီ-",
        KEYS[6]: "ဤရေဒီယိုလိုင်းနှင့် ၎င်း၏နိုင်ငံကို အပ်ဒိတ်လုပ်ရန် တည်းဖြတ်မှုကို ဖွင့်ပါ",
        KEYS[7]: "<small>• အုပ်စုခွဲများနှင့် လိုင်းများကို စူးစမ်းရန် ဖိုင်တွဲများ <b>[▶]</b> ကို ချဲ့ပါ။\n• ပြန်လည်စီစဉ်ရန် <b>အပေါ်ရွှေ့ / အောက်ရွှေ့</b> သို့မဟုတ် ဆွဲယူထည့်ပါ။\n• လိုင်းများကို အခြားဖိုင်တွဲသို့ ရွှေ့ရန် <b>သို့ ရွှေ့ပါ...</b> ကို သုံးပါ။</small>",
        KEYS[8]: "TiMonde သည် <b>/</b> ခြားနားချက်ဖြင့် လမ်းကြောင်းစည်းမျဉ်းများကို သုံးပါသည်-\n\n• <b>/</b> သို့မဟုတ် <b>(Root)</b> : လိုင်းကို မီနူးရင်းတွင် ထားရှိပါသည် (အုပ်စုမပါ)။\n• <b>/ဂါဘွန်</b> သို့မဟုတ် <b>ဂါဘွန်</b> : « ဂါဘွန် » အုပ်စုတွင် ထားရှိပါသည်။\n\n<i>အုပ်စုများ မရှိသေးပါက အလိုအလျောက် ဖန်တီးပေးပါသည်။</i>"
    },
    "bn": {
        KEYS[0]: "ইনস্টল করা বাইনারি ফাইল:",
        KEYS[1]: "TiMonde সংস্করণ",
        KEYS[2]: "[সাময়িক]",
        KEYS[3]: "জমা দেওয়া হয়েছে",
        KEYS[4]: "স্টেশন সম্পাদনা করুন",
        KEYS[5]: "স্টেশন মুছে ফেলা হয়েছে:",
        KEYS[6]: "এই স্টেশন এবং এর দেশ আপডেট করতে সম্পাদক খুলুন",
        KEYS[7]: "<small>• সাবগ্রুপ এবং স্টেশন দেখতে ফোল্ডার <b>[▶]</b> প্রসারিত করুন।\n• পুনর্বিন্যাস করতে <b>উপরে / নিচে সরান</b> অথবা টেনে আনুন।\n• স্টেশন অন্য ফোল্ডারে নিতে <b>এখানে সরান...</b> ব্যবহার করুন।</small>",
        KEYS[8]: "TiMonde <b>/</b> বিভাজক দিয়ে পাথ নিয়ম ব্যবহার করে:\n\n• <b>/</b> বা <b>(রুট)</b> : স্টেশনটিকে মেনুর মূলে রাখে (গ্রুপ ছাড়া)।\n• <b>/গ্যাবন</b> বা <b>গ্যাবন</b> : স্টেশনটিকে « গ্যাবন » গ্রুপে রাখে।\n\n<i>গ্রুপ না থাকলে স্বয়ংক্রিয়ভাবে তৈরি হয়।</i>"
    },
    "ne": {
        KEYS[0]: "स्थापना गरिएको बाइनरी फाइल:",
        KEYS[1]: "TiMonde संस्करण",
        KEYS[2]: "[अस्थायी]",
        KEYS[3]: "पेश गरियो",
        KEYS[4]: "स्टेशन सम्पादन गर्नुहोस्",
        KEYS[5]: "स्टेशन मेटाइयो:",
        KEYS[6]: "यो स्टेशन र यसको देश अपडेट गर्न सम्पादक खोल्नुहोस्",
        KEYS[7]: "<small>• उपसमूह र स्टेशनहरू हेर्न फोल्डरहरू <b>[▶]</b> विस्तार गर्नुहोस्।\n• पुन: क्रमबद्ध गर्न <b>माथि / तल सार्नुहोस्</b> वा तान्नुहोस्।\n• स्टेशन अर्को फोल्डरमा सार्न <b>यहाँ सार्नुहोस्...</b> प्रयोग गर्नुहोस्।</small>",
        KEYS[8]: "TiMonde ले <b>/</b> विभाजकको साथ मार्ग नियमहरू प्रयोग गर्दछ:\n\n• <b>/</b> वा <b>(रूट)</b> : स्टेशनलाई मेनुको मूलमा राख्छ (समूह बिना)।\n• <b>/गाबोन</b> वा <b>गाबोन</b> : स्टेशनलाई « गाबोन » समूहमा राख्छ।\n\n<i>समूहहरू पहिले नै अवस्थित नभएमा स्वतः सिर्जना हुन्छन्।</i>"
    },
    "si": {
        KEYS[0]: "ස්ථාපිත ද්විමය ගොනුව:",
        KEYS[1]: "TiMonde අනුවාදය",
        KEYS[2]: "[තාවකාලික]",
        KEYS[3]: "ඉදිරිපත් කරන ලදී",
        KEYS[4]: "නාලිකාව සංස්කරණය කරන්න",
        KEYS[5]: "නාලිකාව මකා දමන ලදී:",
        KEYS[6]: "මෙම නාලිකාව සහ එහි රට යාවත්කාලීන කිරීමට සංස්කාරකය විවෘත කරන්න",
        KEYS[7]: "<small>• උප සමූහ සහ නාලිකා ගවේෂණය කිරීමට ෆෝල්ඩර <b>[▶]</b> පුළුල් කරන්න.\n• නැවත ඇණවුම් කිරීමට <b>ඉහළට / පහළට ගෙන යන්න</b> හෝ අදින්න.\n• නාලිකා වෙනත් ෆෝල්ඩරයකට ගෙන යාමට <b>වෙත ගෙන යන්න...</b> භාවිතා කරන්න.</small>",
        KEYS[8]: "TiMonde <b>/</b> බෙදුම්කරු සමඟ මාර්ග සම්මුතීන් භාවිතා කරයි:\n\n• <b>/</b> හෝ <b>(මූල)</b> : නාලිකාව මෙනු මූලයේ තබයි (කණ්ඩායමක් නොමැතිව).\n• <b>/ගැබොන්</b> හෝ <b>ගැබොන්</b> : නාලිකාව « ගැබොන් » කණ්ඩායමේ තබයි.\n\n<i>කණ්ඩායම් නොමැති නම් ස්වයංක්‍රීයව සෑදේ.</i>"
    },
    "am": {
        KEYS[0]: "የተጫነ ሁለትዮሽ ፋይል፦",
        KEYS[1]: "የ TiMonde ስሪት",
        KEYS[2]: "[ጊዜያዊ]",
        KEYS[3]: "ገብቷል",
        KEYS[4]: "ጣቢያውን ያርትዑ",
        KEYS[5]: "ጣቢያው ተሰርዟል፦",
        KEYS[6]: "ይህን ጣቢያ እና ሀገሩን ለማዘመን አርታዒውን ይክፈቱ",
        KEYS[7]: "<small>• ንዑስ ቡድኖችን እና ጣቢያዎችን ለማሰስ አቃፊዎችን <b>[▶]</b> ዘርጋ።\n• እንደገና ለማስተካከል <b>ወደ ላይ / ወደ ታች ውሰድ</b> ወይም ጎትተህ ጣል ተጠቀም።\n• ጣቢያዎችን ወደ ሌላ አቃፊ ለማደራጀት <b>ወደ... ውሰድ</b> ተጠቀም።</small>",
        KEYS[8]: "TiMonde የ <b>/</b> መለያያ የመንገድ ደንቦችን ይጠቀማል፦\n\n• <b>/</b> ወይም <b>(ስር)</b> ፦ ጣቢያውን በምናሌው ስር ያስቀምጣል (ያለ ቡድን)።\n• <b>/ጋቦን</b> ወይም <b>ጋቦን</b> ፦ ጣቢያውን በ « ጋቦን » ቡድን ውስጥ ያስቀምጣል።\n\n<i>ቡድኖች አስቀድመው ካልነበሩ በራስ-ሰр ይፈጠራሉ።</i>"
    }
}


def update_po_translations(po_path, translations_dict):
    """Met à jour les msgstr dans un fichier .po pour les msgid correspondants."""
    with open(po_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split("\n\n")
    updated_blocks = []
    updated_count = 0

    for b in blocks:
        if not b.strip():
            continue

        id_lines = []
        is_msgid = False
        for l in b.split("\n"):
            if l.startswith("msgid "):
                is_msgid = True
                id_lines.append(l[6:].strip())
            elif is_msgid and l.startswith("\""):
                id_lines.append(l.strip())
            elif is_msgid:
                break

        if id_lines:
            try:
                full_id = "".join([ast.literal_eval(x) for x in id_lines])
            except Exception:
                full_id = "".join([x.strip("\"") for x in id_lines])

            if full_id in translations_dict:
                new_val = translations_dict[full_id]
                updated_count += 1

                if "\n" not in new_val:
                    esc = json.dumps(new_val, ensure_ascii=False)[1:-1]
                    str_lines = [f"msgstr \"{esc}\""]
                else:
                    str_lines = ["msgstr \"\""]
                    parts = new_val.split("\n")
                    for idx, p in enumerate(parts):
                        esc = json.dumps(p, ensure_ascii=False)[1:-1]
                        suffix = "\\n" if idx < len(parts) - 1 else ""
                        str_lines.append(f"\"{esc}{suffix}\"")

                old_msgid_part = b.split("msgstr")[0].strip()
                new_block = old_msgid_part + "\n" + "\n".join(str_lines)
                updated_blocks.append(new_block)
                continue

        updated_blocks.append(b)

    with open(po_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(updated_blocks) + "\n\n")

    return updated_count


def main():
    total_files_updated = 0
    total_translations_applied = 0

    for lang, translations in ALL_CLUSTER_TRANSLATIONS.items():
        po_path = os.path.join(PO_DIR, f"{lang}.po")
        if os.path.exists(po_path):
            nb = update_po_translations(po_path, translations)
            print(f"[{lang:5s}] {nb} clés mises à jour avec les traductions réelles.")
            total_files_updated += 1
            total_translations_applied += nb

    print("-" * 60)
    print(f"Total langues mises à jour : {total_files_updated}")
    print(f"Total traductions natives injectées : {total_translations_applied}")


if __name__ == "__main__":
    main()
