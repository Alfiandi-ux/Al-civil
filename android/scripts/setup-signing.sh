#!/usr/bin/env bash
# Menyiapkan keystore rilis AL-CIVIL satu kali, lalu mengunggahnya ke GitHub Secrets.
# Jalankan dari mana saja: ./android/scripts/setup-signing.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$ANDROID_DIR/.." && pwd)"
KEYSTORE="$ANDROID_DIR/app/release.keystore"
PROPS="$ANDROID_DIR/keystore.properties"
ALIAS="${ANDROID_KEY_ALIAS:-alcivil}"
DNAME="${ANDROID_KEY_DNAME:-CN=AL-CIVIL WMS, OU=Civil, O=AlCivil, L=Jakarta, C=ID}"

if ! command -v keytool >/dev/null 2>&1; then
  echo "ERROR: keytool tidak ditemukan. Pasang JDK (Termux: pkg install openjdk-21)." >&2
  exit 1
fi

valid_password() {
  [[ "$1" =~ ^[A-Za-z0-9._-]{6,}$ ]]
}

echo "============================================================"
echo "  AL-CIVIL — Setup Kunci Tanda Tangan APK"
echo "============================================================"

if [ -f "$KEYSTORE" ]; then
  echo "Keystore sudah ada: $KEYSTORE"
  echo "Skrip akan memakai file yang sama (jangan diganti agar update APK tetap valid)."
  PASS="${ANDROID_KEYSTORE_PASSWORD:-}"
  if [ -z "$PASS" ]; then
    read -rsp "Masukkan password keystore yang ada: " PASS
    echo
  fi
  valid_password "$PASS" || {
    echo "ERROR: password hanya boleh huruf, angka, titik, garis bawah, strip (min. 6)." >&2
    exit 1
  }
  if ! keytool -list -keystore "$KEYSTORE" -alias "$ALIAS" -storepass "$PASS" >/dev/null 2>&1; then
    echo "ERROR: alias '$ALIAS' tidak ada atau password salah." >&2
    exit 1
  fi
else
  PASS="${ANDROID_KEYSTORE_PASSWORD:-}"
  if [ -z "$PASS" ]; then
    while :; do
      read -rsp "Buat password keystore baru (min. 6 karakter): " PASS
      echo
      read -rsp "Ulangi password: " PASS2
      echo
      if ! valid_password "$PASS"; then
        echo "Gunakan hanya huruf, angka, titik, garis bawah, strip (min. 6)."
      elif [ "$PASS" != "$PASS2" ]; then
        echo "Password tidak cocok, coba lagi."
      else
        break
      fi
    done
  fi
  valid_password "$PASS" || {
    echo "ERROR: password hanya boleh huruf, angka, titik, garis bawah, strip (min. 6)." >&2
    exit 1
  }

  echo "Membuat keystore baru (RSA 2048, berlaku 10.000 hari)..."
  keytool -genkeypair \
    -keystore "$KEYSTORE" \
    -storetype PKCS12 \
    -alias "$ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass "$PASS" \
    -keypass "$PASS" \
    -dname "$DNAME"
fi

umask 077
cat > "$PROPS" <<EOF
storeFile=release.keystore
storePassword=$PASS
keyAlias=$ALIAS
keyPassword=$PASS
EOF
chmod 600 "$PROPS" "$KEYSTORE"

echo
echo "Fingerprint keystore (catat untuk verifikasi rilis):"
keytool -list -v -keystore "$KEYSTORE" -alias "$ALIAS" -storepass "$PASS" \
  | grep -E "SHA1:|SHA256:" || true

echo
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  REPO="$(git -C "$REPO_ROOT" remote get-url origin \
    | sed -E 's#.*github\.com[:/]([^/]+/[^/.]+)(\.git)?$#\1#')"
  echo "Mengunggah 4 secret ke GitHub: $REPO"
  base64 < "$KEYSTORE" | tr -d '\n' | gh secret set ANDROID_KEYSTORE_BASE64 --repo "$REPO"
  printf '%s' "$PASS" | gh secret set ANDROID_KEYSTORE_PASSWORD --repo "$REPO"
  printf '%s' "$ALIAS" | gh secret set ANDROID_KEY_ALIAS --repo "$REPO"
  printf '%s' "$PASS" | gh secret set ANDROID_KEY_PASSWORD --repo "$REPO"
  echo "Selesai. Push ke main (atau jalankan workflow manual) untuk membangun APK."
else
  echo "GitHub CLI (gh) belum terpasang/login."
  echo "Jalankan 'gh auth login', lalu ulangi skrip ini untuk mengunggah secret otomatis."
  echo
  echo "Atau set manual 4 secret berikut di:"
  echo "  https://github.com/<owner>/<repo>/settings/secrets/actions"
  echo "  - ANDROID_KEYSTORE_BASE64   : $(base64 < "$KEYSTORE" | tr -d '\n' | wc -c) karakter base64"
  echo "  - ANDROID_KEYSTORE_PASSWORD : (password yang Anda masukkan)"
  echo "  - ANDROID_KEY_ALIAS         : $ALIAS"
  echo "  - ANDROID_KEY_PASSWORD      : (sama dengan password keystore)"
fi

echo
echo "PENTING: cadangkan $KEYSTORE dan password-nya (mis. ke password manager)."
echo "Jika file ini hilang, APK baru tidak bisa memperbarui aplikasi yang sudah terpasang."
