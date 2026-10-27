# Panduan Membangun Backend Monitoring Lab di Laravel

Dokumen ini berisi langkah-langkah dan kode siap pakai ketika Anda ingin menggantikan `server.py` (Flask) menjadi aplikasi **Laravel + MySQL** yang memiliki fitur Login Staf IT.

> **Catatan:** File `agent.py` (baik `.exe` maupun `.deb`) **tidak perlu diubah sama sekali** saat Anda pindah ke Laravel. Anda cukup mengarahkan alamat server di `agent` ke alamat/domain aplikasi Laravel Anda.

---

## 1. Struktur Data yang Dikirim oleh `agent.py`
Setiap 3 detik, `agent.py` mengirimkan `POST` JSON ke endpoint `/api/monitoring` dengan struktur berikut:

```json
{
  "mac_address": "64:C9:01:F3:89:37",
  "local_ip": "172.17.80.171",
  "hostname": "LAB-PC-01",
  "os_version": "Windows 10",
  "cpu_percent": 12.5,
  "ram_percent": 45.2,
  "storage_free_gb": 110.4,
  "is_online": true,
  "uptime": "3j 15m",
  "active_user": "praktikan",
  "top_process": "chrome.exe (8.2%)",
  "peripherals": {
    "mouse": true,
    "keyboard": true,
    "audio": true,
    "monitor": true
  },
  "usb_drives": [
    "SanDisk Cruzer (14.9 GB)"
  ],
  "connected_devices": [
    "SIGMACHIP Usb Mouse",
    "USB Keyboard"
  ]
}
```

---

## 2. Buat Model & Migration di Laravel

Jalankan perintah berikut di terminal project Laravel Anda:
```bash
php artisan make:model Computer -m
```

Buka file migration di `database/migrations/xxxx_xx_xx_create_computers_table.php` dan isi seperti berikut:

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('computers', function (Blueprint $table) {
            $table->id();
            $table->string('mac_address')->unique();
            $table->string('hostname')->nullable();
            $table->string('local_ip')->nullable();
            $table->string('os_version')->nullable();
            $table->float('cpu_percent')->default(0);
            $table->float('ram_percent')->default(0);
            $table->float('storage_free_gb')->default(0);
            $table->boolean('is_online')->default(true);
            $table->string('uptime')->nullable();
            $table->string('active_user')->nullable();
            $table->string('top_process')->nullable();
            $table->json('peripherals')->nullable();
            $table->json('usb_drives')->nullable();
            $table->json('connected_devices')->nullable();
            $table->string('pending_command')->nullable(); // Menyimpan antrean 'shutdown' atau 'restart'
            $table->timestamp('last_seen')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('computers');
    }
};
```

Lalu jalankan migrasi database:
```bash
php artisan migrate
```

---

## 3. Isi Model `app/Models/Computer.php`

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Computer extends Model
{
    protected $fillable = [
        'mac_address',
        'hostname',
        'local_ip',
        'os_version',
        'cpu_percent',
        'ram_percent',
        'storage_free_gb',
        'is_online',
        'uptime',
        'active_user',
        'top_process',
        'peripherals',
        'usb_drives',
        'connected_devices',
        'pending_command',
        'last_seen',
    ];

    protected $casts = [
        'is_online' => 'boolean',
        'peripherals' => 'array',
        'usb_drives' => 'array',
        'connected_devices' => 'array',
        'last_seen' => 'datetime',
    ];
}
```

---

## 4. Buat Controller `MonitoringController.php`

Jalankan perintah:
```bash
php artisan make:controller MonitoringController
```

Isi `app/Http/Controllers/MonitoringController.php`:

```php
<?php

namespace App\Http\Controllers;

use App\Models\Computer;
use Illuminate\Http\Request;

class MonitoringController extends Controller
{
    /**
     * Menerima data dari agent.py (POST /api/monitoring)
     */
    public function store(Request $request)
    {
        $mac = $request->input('mac_address', 'unknown');
        $existing = Computer::where('mac_address', $mac)->first();
        $command = $existing ? $existing->pending_command : null;

        Computer::updateOrCreate(
            ['mac_address' => $mac],
            [
                'hostname'          => $request->input('hostname'),
                'local_ip'          => $request->input('local_ip'),
                'os_version'        => $request->input('os_version'),
                'cpu_percent'       => $request->input('cpu_percent', 0),
                'ram_percent'       => $request->input('ram_percent', 0),
                'storage_free_gb'   => $request->input('storage_free_gb', 0),
                'is_online'         => $request->input('is_online', true),
                'uptime'            => $request->input('uptime', '-'),
                'active_user'       => $request->input('active_user', '-'),
                'top_process'       => $request->input('top_process', '-'),
                'peripherals'       => $request->input('peripherals', [
                    'mouse' => false,
                    'keyboard' => false,
                    'audio' => false,
                    'monitor' => false,
                ]),
                'usb_drives'        => $request->input('usb_drives', []),
                'connected_devices' => $request->input('connected_devices', []),
                'pending_command'   => null, // Kosongkan antrean setelah dikirim ke agent.py
                'last_seen'         => now(),
            ]
        );

        return response()->json([
            'status'  => 'success',
            'command' => $command,
        ], 200);
    }

    /**
     * Menerima perintah Shutdown / Restart per PC dari Dashboard (POST /api/command)
     */
    public function sendCommand(Request $request)
    {
        $request->validate([
            'mac_address' => 'required|string',
            'command'     => 'required|in:shutdown,restart',
        ]);

        Computer::where('mac_address', $request->mac_address)
            ->update(['pending_command' => $request->command]);

        return response()->json(['status' => 'success']);
    }

    /**
     * Mengirimkan daftar PC ke tampilan Dashboard (GET /api/monitoring)
     */
    public function index()
    {
        $computers = Computer::orderBy('hostname')->get()->map(function ($pc) {
            $diff = $pc->last_seen ? now()->diffInSeconds($pc->last_seen) : 999;

            if ($diff > 30) {
                $status = 'Offline';
            } elseif ($pc->cpu_percent > 90 || $pc->ram_percent > 90) {
                $status = 'Warning';
            } else {
                $status = 'Online';
            }

            $data = $pc->toArray();
            $data['status'] = $status;
            $data['last_seen'] = $pc->last_seen ? $pc->last_seen->format('Y-m-d H:i:s') : '-';
            return $data;
        });

        return response()->json($computers);
    }
}
```

---

## 5. Daftarkan Route API & Route Web (dengan Login)

### A. Route API (`routes/api.php`)
*(Pada Laravel 11/12, jika `routes/api.php` belum ada, jalankan `php artisan install:api` terlebih dahulu).*

```php
<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\MonitoringController;

Route::post('/monitoring', [MonitoringController::class, 'store']);
Route::get('/monitoring', [MonitoringController::class, 'index']);
Route::post('/command', [MonitoringController::class, 'sendCommand']);
```

### B. Route Web dengan Login (`routes/web.php`)
Untuk membuat sistem Login dengan cepat di Laravel, Anda bisa menginstal **Laravel Breeze**:
```bash
composer require laravel/breeze --dev
php artisan breeze:install blade
npm install && npm run build
php artisan migrate
```

Lalu di `routes/web.php`, lindungi halaman dashboard dengan middleware `auth`:
```php
Route::middleware(['auth'])->group(function () {
    Route::get('/dashboard', function () {
        return view('monitoring'); // Salin isi templates/index.html ke resources/views/monitoring.blade.php
    })->name('dashboard');
});
```
