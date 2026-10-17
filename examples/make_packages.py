"""Build the two example ZIPs next to this script: python examples/make_packages.py."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
for directory in (root / 'A2-robot-demo', root / 'A2-full-demo'):
    destination = root / f'{directory.name}.zip'
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for file in sorted(directory.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
                archive.write(file, file.relative_to(root))
    print(destination)
