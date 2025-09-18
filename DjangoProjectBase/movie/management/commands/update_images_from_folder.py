import os
import re
import unicodedata
from difflib import get_close_matches
from django.core.management.base import BaseCommand
from movie.models import Movie


class Command(BaseCommand):
    help = "Assign images from media/movie/images/ folder to movies in the database (tolerant matching)"

    def handle(self, *args, **kwargs):
        images_folder = os.path.join('media', 'movie', 'images')
        if not os.path.exists(images_folder):
            self.stderr.write(f"Images folder '{images_folder}' not found.")
            return

        all_files = [f for f in os.listdir(images_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        all_files_lower = {f.lower(): f for f in all_files}  

        basenames_noext_lower = {os.path.splitext(f.lower())[0]: f for f in all_files}

        self.stdout.write(f"Found {len(all_files)} image files in folder")

        updated = 0
        movies = Movie.objects.all()
        self.stdout.write(f"Found {movies.count()} movies in database")

        for movie in movies:
            variants = self._filename_variants(movie.title)

            found_file = None

            for base in variants:
                for ext in ('.png', '.jpg', '.jpeg', '.webp'):
                    candidate = f"{base}{ext}"
                    m_candidate = f"m_{candidate}"
                    if m_candidate.lower() in all_files_lower:
                        found_file = all_files_lower[m_candidate.lower()]
                        break
                    if candidate.lower() in all_files_lower:
                        found_file = all_files_lower[candidate.lower()]
                        break
                if found_file:
                    break

            if not found_file:
                ref = variants[0]
                candidates = list(basenames_noext_lower.keys())
                for ref_try in (ref, f"m_{ref}"):
                    close = get_close_matches(ref_try.lower(), candidates, n=1, cutoff=0.75)
                    if close:
                        found_file = basenames_noext_lower[close[0]]
                        break

            if found_file:
                rel_path = os.path.join('movie', 'images', found_file)
                movie.image = rel_path
                movie.save()
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"Updated: {movie.title} → {found_file}"))
            else:
                self.stderr.write(f"Image not found for: {movie.title} (tried: {', '.join([f'm_{v}.png' for v in variants[:3]])}...)")

        self.stdout.write(self.style.SUCCESS(f"Finished updating {updated} movies."))


    def _normalize_ascii(self, s: str) -> str:
        """
        Remove Acents and other non-ASCII characters
        """
        if not s:
            return s
        s = unicodedata.normalize('NFKD', s)
        s = s.encode('ascii', 'ignore').decode('ascii')
        return s

    def _basic_clean(self, s: str) -> str:
        """
        Clean problematic punctuation and spaces. Keeps letters/numbers/_/-/.
        """
        s = s.strip()
        # Reemplaza separadores comunes por espacio
        s = s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
        s = s.replace('&', ' and ')
        # Elimina signos que suelen no estar en los archivos
        s = re.sub(r"[^\w\s\.-]", " ", s)  # fuera de \w (alfa-numérico y _), espacio, . y -
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _to_filename_core(self, title: str) -> str:
        """
        transform the title to filename core 'Alice_in_Wonderland'
        (without 'm_' prefix or extension).
        """
        s = self._normalize_ascii(title)
        s = self._basic_clean(s)
        # Une con underscore
        s = s.replace(' ', '_')
        # Evita dobles underscores
        s = re.sub(r"_+", "_", s)
        return s

    def _filename_variants(self, title: str):
        """
        Generate a set of probable variants of the basename (without extension),
        to cover differences in punctuation/language.
        """
        base = self._to_filename_core(title)

        variants = set()
        variants.add(base)

        # Variant without 'The_' prefix
        if base.lower().startswith('the_'):
            variants.add(base[4:])

        # Variant without Spanish articles 'El_', 'La_', 'Los_', 'Las_'
        for art in ('el_', 'la_', 'los_', 'las_'):
            if base.lower().startswith(art):
                variants.add(base[len(art):])

        # Variant without French articles 'le_', 'la_', 'les_', or apostrophes
        for art in ('le_', 'la_', 'les_'):
            if base.lower().startswith(art):
                variants.add(base[len(art):])

        # Variant with hyphens instead of underscores (in case files come like this)
        variants.add(base.replace('_', '-'))

        # Variant without very short problematic words (like a/of/the)
        tokens = base.split('_')
        if len(tokens) > 2:
            filtered = [t for t in tokens if t.lower() not in {'a', 'of', 'the', 'and'}]
            if filtered:
                variants.add('_'.join(filtered))

        # Variant without very short problematic words (like a/of/the)
        if '_' in base:
            variants.add(base.split('_', 1)[0])

        # Return in stable order (first is the most "faithful")
        return [v for v in [base] + list(variants - {base}) if v]
    

