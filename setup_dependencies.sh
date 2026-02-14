#!/bin/bash

echo "============================================"
echo "  Agent Dzeck AI - Auto Install Dependencies"
echo "============================================"
echo ""

FAILED_PACKAGES=()
SUCCESS_COUNT=0
FAIL_COUNT=0

PIP_FLAGS="--break-system-packages --no-cache-dir"

check_command() {
  command -v "$1" >/dev/null 2>&1
}

install_pkg() {
  local pkg="$1"
  echo -n "  [$((SUCCESS_COUNT + FAIL_COUNT + 1))] $pkg ... "
  pip install $PIP_FLAGS -q "$pkg" >/dev/null 2>&1
  local status=$?
  if [ $status -eq 0 ]; then
    echo "OK"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  else
    echo "GAGAL"
    FAILED_PACKAGES+=("$pkg")
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  return $status
}

echo "[1/6] Mengecek Python..."
if check_command python3; then
  PYTHON=python3
elif check_command python; then
  PYTHON=python
else
  echo "  ERROR: Python tidak ditemukan!"
  exit 1
fi
echo "  -> $($PYTHON --version)"
echo "  -> pip: $(pip --version 2>/dev/null | head -1 || echo 'tidak ditemukan')"

echo ""
echo "[2/6] Upgrade pip & setuptools..."
pip install $PIP_FLAGS --upgrade pip setuptools wheel >/dev/null 2>&1
echo "  -> Selesai"

echo ""
echo "[3/6] Install paket Core..."

CORE_PACKAGES=(
  "fastapi"
  "uvicorn[standard]"
  "aiofiles"
  "pydantic"
  "pydantic-core"
  "python-dotenv"
  "requests"
  "httpx"
  "numpy"
  "colorama"
  "termcolor"
  "tqdm"
  "sniffio"
  "distro"
  "certifi"
  "openai"
  "configparser"
  "langid"
  "pypinyin"
  "pypdf"
  "ipython"
  "anyio"
  "jiter"
  "protobuf"
  "ordered-set"
  "rich"
  "emoji"
  "nltk"
  "regex"
  "pillow"
  "markdown-it-py"
  "flask"
  "jinja2"
)

for pkg in "${CORE_PACKAGES[@]}"; do
  install_pkg "$pkg"
done
echo "  -> Core selesai."

echo ""
echo "[4/6] Install paket Browser..."

BROWSER_PACKAGES=(
  "selenium"
  "selenium-stealth"
  "undetected-chromedriver"
  "chromedriver-autoinstaller"
  "beautifulsoup4"
  "markdownify"
  "fake-useragent"
)

for pkg in "${BROWSER_PACKAGES[@]}"; do
  install_pkg "$pkg"
done
echo "  -> Browser selesai."

echo ""
echo "[5/6] Install paket ML & AI Provider..."

echo "  Installing PyTorch (CPU)..."
pip install $PIP_FLAGS -q torch --index-url https://download.pytorch.org/whl/cpu >/dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "  -> PyTorch OK"
  SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
else
  echo "  -> PyTorch gagal dari CPU index, coba default..."
  pip install $PIP_FLAGS -q torch >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "  -> PyTorch OK (fallback)"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
  else
    echo "  -> PyTorch GAGAL"
    FAILED_PACKAGES+=("torch")
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
fi

ML_PACKAGES=(
  "transformers"
  "adaptive-classifier"
  "sentencepiece"
  "sacremoses"
  "scipy"
  "scikit-learn"
  "safetensors"
  "huggingface-hub"
  "tokenizers"
)

for pkg in "${ML_PACKAGES[@]}"; do
  install_pkg "$pkg"
done
echo "  -> ML & Provider selesai."

echo ""
echo "[6/6] Verifikasi semua modul..."
$PYTHON << 'PYEOF'
import importlib

modules = {
    'fastapi': 'FastAPI',
    'uvicorn': 'Uvicorn',
    'requests': 'Requests',
    'httpx': 'HTTPX',
    'bs4': 'BeautifulSoup4',
    'numpy': 'NumPy',
    'openai': 'OpenAI',
    'torch': 'PyTorch',
    'transformers': 'Transformers',
    'adaptive_classifier': 'AdaptiveClassifier',
    'selenium': 'Selenium',
    'langid': 'LangID',
    'scipy': 'SciPy',
    'sentencepiece': 'SentencePiece',
    'safetensors': 'SafeTensors',
    'PIL': 'Pillow',
    'pydantic': 'Pydantic',
    'dotenv': 'python-dotenv',
    'aiofiles': 'AioFiles',
    'markdownify': 'Markdownify',
    'colorama': 'Colorama',
    'termcolor': 'Termcolor',
    'tqdm': 'TQDM',
    'huggingface_hub': 'HuggingFace Hub',
    'sklearn': 'Scikit-Learn',
    'tokenizers': 'Tokenizers',
    'rich': 'Rich',
    'emoji': 'Emoji',
    'nltk': 'NLTK',
    'regex': 'Regex',
    'sacremoses': 'Sacremoses',
    'pypdf': 'PyPDF',
    'IPython': 'IPython',
    'ordered_set': 'OrderedSet',
}

ok = 0
fail = 0
for mod, name in modules.items():
    try:
        importlib.import_module(mod)
        print(f'  [OK] {name}')
        ok += 1
    except ImportError:
        print(f'  [MISSING] {name}')
        fail += 1

print(f'\n  Hasil: {ok}/{ok+fail} modul terverifikasi')
if fail > 0:
    print(f'  PERINGATAN: {fail} modul belum terinstall')
else:
    print('  SUKSES: Semua modul terinstall!')
PYEOF

echo ""
echo "============================================"
echo "  RINGKASAN INSTALASI"
echo "============================================"

if [ ${#FAILED_PACKAGES[@]} -gt 0 ]; then
  echo ""
  echo "  PERINGATAN: ${FAIL_COUNT} paket gagal install:"
  for pkg in "${FAILED_PACKAGES[@]}"; do
    echo "    - $pkg"
  done
fi

echo ""
echo "  Total: $((SUCCESS_COUNT + FAIL_COUNT)) paket diproses"
echo "  Berhasil: ${SUCCESS_COUNT}"
echo "  Gagal: ${FAIL_COUNT}"
echo ""

if [ -f "config.ini" ]; then
  echo "  config.ini: OK"
else
  echo "  PERINGATAN: config.ini tidak ditemukan!"
fi

WORK_DIR=$(grep "work_dir" config.ini 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
if [ -n "$WORK_DIR" ]; then
  mkdir -p "$WORK_DIR" 2>/dev/null
  echo "  work_dir ($WORK_DIR): OK"
fi

echo ""
echo "[EXTRA] Rebuild frontend jika diperlukan..."
if [ -d "frontend/agentic-seek-front" ]; then
  cd frontend/agentic-seek-front
  if check_command npm; then
    echo "  Installing npm dependencies..."
    npm install --silent 2>/dev/null
    echo "  Building frontend..."
    npx react-scripts build 2>/dev/null
    if [ $? -eq 0 ]; then
      echo "  -> Frontend build OK"
    else
      echo "  -> Frontend build GAGAL (non-critical)"
    fi
    cd ../..
  else
    echo "  -> npm tidak ditemukan, skip frontend build"
    cd ../..
  fi
else
  echo "  -> Folder frontend tidak ditemukan, skip"
fi

echo ""
echo "  Selesai! Jalankan: python api.py"
echo "============================================"
