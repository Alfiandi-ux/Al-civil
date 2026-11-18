package com.alcivil.wms;

import android.Manifest;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends AppCompatActivity {

    private static final int FILE_CHOOSER_REQUEST_CODE = 1001;
    private static final int CAMERA_PERMISSION_REQUEST_CODE = 1002;
    private static final String PREF_NAME = "alcivil_config";
    private static final String KEY_SERVER_URL = "custom_server_url";

    private WebView webView;
    private View splashLayout;
    private TextView txtStatus;
    private TextView txtSubStatus;
    private Button btnSwitchServer;

    private ValueCallback<Uri[]> mFilePathCallback;
    private PermissionRequest pendingCameraRequest;
    private long lastBackPressTime = 0;
    private boolean isServerStarted = false;
    private String activeServerUrl = "http://127.0.0.1:5000";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        splashLayout = findViewById(R.id.splashLayout);
        txtStatus = findViewById(R.id.txtStatus);
        txtSubStatus = findViewById(R.id.txtSubStatus);
        btnSwitchServer = findViewById(R.id.btnSwitchServer);

        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        String customUrl = prefs.getString(KEY_SERVER_URL, null);

        setupWebView();

        btnSwitchServer.setOnClickListener(v -> showServerConfigDialog());

        // Jika user telah mengatur URL server eksternal, langsung hubungkan
        if (customUrl != null && !customUrl.trim().isEmpty() && !customUrl.contains("127.0.0.1")) {
            activeServerUrl = customUrl.trim();
            txtStatus.setText("Menghubungkan ke Server Eksternal…");
            txtSubStatus.setText(activeServerUrl);
            checkAndLoadUrl(activeServerUrl, 0);
        } else {
            // Mode Lokal Mandiri (Chaquopy + Python Flask Server)
            startLocalPythonServer();
        }

        // Tampilkan tombol ubah server setelah 6 detik jika server lambat boot
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (splashLayout.getVisibility() == View.VISIBLE) {
                btnSwitchServer.setVisibility(View.VISIBLE);
            }
        }, 6000);
    }

    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);

        CookieManager.getInstance().setAcceptCookie(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    return false; // Load inside WebView
                }
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                    startActivity(intent);
                    return true;
                } catch (Exception e) {
                    return false;
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (splashLayout.getVisibility() == View.VISIBLE) {
                    splashLayout.setVisibility(View.GONE);
                    webView.setVisibility(View.VISIBLE);
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            // Barcode Scanner Kamera Permission
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                for (String res : request.getResources()) {
                    if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(res)) {
                        if (ContextCompat.checkSelfPermission(MainActivity.this, Manifest.permission.CAMERA)
                                == PackageManager.PERMISSION_GRANTED) {
                            request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                        } else {
                            pendingCameraRequest = request;
                            ActivityCompat.requestPermissions(MainActivity.this,
                                    new String[]{Manifest.permission.CAMERA},
                                    CAMERA_PERMISSION_REQUEST_CODE);
                        }
                        return;
                    }
                }
                request.grant(request.getResources());
            }

            // File Chooser untuk Upload File Restore Database / CSV
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback,
                                             FileChooserParams fileChooserParams) {
                if (mFilePathCallback != null) {
                    mFilePathCallback.onReceiveValue(null);
                }
                mFilePathCallback = filePathCallback;

                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                // Wajib agar WebView di proses yang sama boleh membaca
                // content:// URI hasil pilihan (restore .db/.json).
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                startActivityForResult(Intent.createChooser(intent, "Pilih File Database / JSON"), FILE_CHOOSER_REQUEST_CODE);
                return true;
            }
        });

        // Download Listener untuk Export CSV & Backup Database
        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition,
                                        String mimeType, long contentLength) {
                try {
                    DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                    String fileName = URLUtil.guessFileName(url, contentDisposition, mimeType);
                    request.setMimeType(mimeType);
                    request.addRequestHeader("User-Agent", userAgent);
                    request.setTitle(fileName);
                    request.setDescription("Mengunduh dari AL-CIVIL WMS...");
                    request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName);

                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (dm != null) {
                        dm.enqueue(request);
                        Toast.makeText(MainActivity.this, "Mengunduh: " + fileName, Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    // Fallback browser external
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                        startActivity(intent);
                    } catch (Exception ex) {
                        Toast.makeText(MainActivity.this, "Gagal mengunduh: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    }
                }
            }
        });
    }

    private void startLocalPythonServer() {
        new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(getApplicationContext()));
                }

                File dataDir = getFilesDir();
                File backupsDir = new File(dataDir, "backups");
                if (!backupsDir.exists()) {
                    backupsDir.mkdirs();
                }

                Python py = Python.getInstance();
                py.getModule("os").get("environ").callAttr("__setitem__", "ALCIVIL_DATA_DIR", dataDir.getAbsolutePath());

                // Jalankan Flask server pada port 5000
                if (!isServerStarted) {
                    isServerStarted = true;
                    new Thread(() -> {
                        try {
                            py.getModule("app").callAttr("start_android_server", 5000);
                        } catch (Exception e) {
                            e.printStackTrace();
                        }
                    }, "FlaskServerThread").start();
                }

                checkAndLoadUrl("http://127.0.0.1:5000", 0);

            } catch (Exception e) {
                e.printStackTrace();
                runOnUiThread(() -> {
                    txtStatus.setText("Gagal memulai server lokal");
                    txtSubStatus.setText(e.getMessage());
                    btnSwitchServer.setVisibility(View.VISIBLE);
                });
            }
        }).start();
    }

    private void checkAndLoadUrl(String baseUrl, int attempt) {
        new Thread(() -> {
            boolean ready = false;
            try {
                URL testUrl = new URL(baseUrl + "/api/system-status");
                HttpURLConnection conn = (HttpURLConnection) testUrl.openConnection();
                conn.setConnectTimeout(600);
                conn.setReadTimeout(600);
                conn.setRequestMethod("GET");
                int code = conn.getResponseCode();
                ready = (code == 200);
                conn.disconnect();
            } catch (Exception ignored) {
                ready = false;
            }

            if (ready) {
                runOnUiThread(() -> {
                    txtStatus.setText("Membuka aplikasi…");
                    webView.loadUrl(baseUrl + "/dashboard");
                });
            } else {
                if (attempt < 40) { // Coba hingga 20 detik
                    try {
                        Thread.sleep(500);
                    } catch (InterruptedException ignored) {}
                    checkAndLoadUrl(baseUrl, attempt + 1);
                } else {
                    runOnUiThread(() -> {
                        txtStatus.setText("Server belum merespons");
                        txtSubStatus.setText("Periksa server atau hubungkan ke server lain");
                        btnSwitchServer.setVisibility(View.VISIBLE);
                    });
                }
            }
        }).start();
    }

    private void showServerConfigDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this);
        builder.setTitle("Pengaturan Alamat Server");

        final EditText input = new EditText(this);
        input.setHint("http://127.0.0.1:5000 atau http://192.168.x.x:5000");
        input.setText(activeServerUrl);
        builder.setView(input);

        builder.setPositiveButton("Simpan & Hubungkan", (dialog, which) -> {
            String newUrl = input.getText().toString().trim();
            if (!newUrl.isEmpty()) {
                if (!newUrl.startsWith("http://") && !newUrl.startsWith("https://")) {
                    newUrl = "http://" + newUrl;
                }
                activeServerUrl = newUrl;
                SharedPreferences.Editor editor = getSharedPreferences(PREF_NAME, MODE_PRIVATE).edit();
                editor.putString(KEY_SERVER_URL, activeServerUrl);
                editor.apply();

                splashLayout.setVisibility(View.VISIBLE);
                webView.setVisibility(View.GONE);
                txtStatus.setText("Menghubungkan ke " + activeServerUrl);
                txtSubStatus.setText("Mohon tunggu...");
                checkAndLoadUrl(activeServerUrl, 0);
            }
        });

        builder.setNegativeButton("Gunakan Server Lokal Mandiri", (dialog, which) -> {
            activeServerUrl = "http://127.0.0.1:5000";
            SharedPreferences.Editor editor = getSharedPreferences(PREF_NAME, MODE_PRIVATE).edit();
            editor.remove(KEY_SERVER_URL);
            editor.apply();

            splashLayout.setVisibility(View.VISIBLE);
            webView.setVisibility(View.GONE);
            startLocalPythonServer();
        });

        builder.setNeutralButton("Batal", (dialog, which) -> dialog.dismiss());
        builder.show();
    }

    /**
     * Salin content:// URI pilihan pengguna ke cache aplikasi lalu kembalikan
     * URI FileProvider. Ini memastikan WebView selalu bisa membaca file dan
     * nama asli (beserta ekstensi .db/.json) tetap dipertahankan.
     */
    @Nullable
    private Uri copyPickedFileToCache(Uri source) {
        if (source == null) return null;

        String displayName = null;
        try (Cursor cursor = getContentResolver().query(source, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) displayName = cursor.getString(idx);
            }
        } catch (Exception ignored) {
        }
        if (displayName == null || displayName.trim().isEmpty()) {
            displayName = source.getLastPathSegment();
        }
        if (displayName == null || displayName.trim().isEmpty()) {
            displayName = "restore_upload";
        }
        displayName = displayName.replaceAll("[^A-Za-z0-9._-]", "_");

        File dir = new File(getCacheDir(), "restore_uploads");
        if (!dir.exists() && !dir.mkdirs()) return source;

        // Bersihkan file upload lama agar cache tidak menumpuk.
        File[] olds = dir.listFiles();
        if (olds != null) {
            long cutoff = System.currentTimeMillis() - 24L * 60 * 60 * 1000;
            for (File f : olds) {
                if (f.isFile() && f.lastModified() < cutoff) {
                    f.delete();
                }
            }
        }

        File dest = new File(dir, System.currentTimeMillis() + "_" + displayName);
        try (InputStream in = getContentResolver().openInputStream(source);
             OutputStream out = new FileOutputStream(dest)) {
            if (in == null) return source;
            byte[] buffer = new byte[8192];
            int len;
            while ((len = in.read(buffer)) > 0) {
                out.write(buffer, 0, len);
            }
        } catch (Exception e) {
            return source;
        }

        try {
            return FileProvider.getUriForFile(this, getPackageName() + ".fileprovider", dest);
        } catch (Exception e) {
            return source;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            if (mFilePathCallback != null) {
                Uri[] results = null;
                if (resultCode == RESULT_OK && data != null) {
                    if (data.getData() != null) {
                        results = new Uri[]{copyPickedFileToCache(data.getData())};
                    } else if (data.getClipData() != null) {
                        int count = data.getClipData().getItemCount();
                        results = new Uri[count];
                        for (int i = 0; i < count; i++) {
                            results[i] = copyPickedFileToCache(data.getClipData().getItemAt(i).getUri());
                        }
                    }
                }
                mFilePathCallback.onReceiveValue(results);
                mFilePathCallback = null;
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == CAMERA_PERMISSION_REQUEST_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                if (pendingCameraRequest != null) {
                    pendingCameraRequest.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                    pendingCameraRequest = null;
                }
            } else {
                if (pendingCameraRequest != null) {
                    pendingCameraRequest.deny();
                    pendingCameraRequest = null;
                }
                Toast.makeText(this, "Izin kamera diperlukan untuk memindai barcode", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.getVisibility() == View.VISIBLE && webView.canGoBack()) {
            webView.goBack();
        } else {
            if (System.currentTimeMillis() - lastBackPressTime < 2000) {
                super.onBackPressed();
            } else {
                lastBackPressTime = System.currentTimeMillis();
                Toast.makeText(this, getString(R.string.press_again_exit), Toast.LENGTH_SHORT).show();
            }
        }
    }
}
