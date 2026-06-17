#!/usr/bin/env php
<?php
/**
 * SIP-Daemon Call-Handler
 *
 * Wird bei jedem eingehenden Anruf ausgeführt.
 * $argv[1]              = Rufnummer des Anrufers (z.B. +41791234567)
 * $_ENV['CALLER_NUMBER'] = dieselbe Rufnummer
 * $_ENV['SIP_INVITE']   = erster Teil des SIP-INVITE (max. 4096 Zeichen)
 */

$callerNumber = $argv[1] ?? $_ENV['CALLER_NUMBER'] ?? 'unbekannt';
$sipInvite    = $_ENV['SIP_INVITE'] ?? '';

// --- Hier eigene Logik eintragen ---

// Beispiel 1: In Datei loggen
$logLine = date('Y-m-d H:i:s') . " Anruf von: {$callerNumber}" . PHP_EOL;
file_put_contents('/var/log/sip-calls.log', $logLine, FILE_APPEND | LOCK_EX);

// Beispiel 2: Webhook aufrufen
/*
$url     = 'https://mein-server.example.com/webhook/call';
$payload = json_encode(['caller' => $callerNumber, 'timestamp' => time()]);

$context = stream_context_create([
    'http' => [
        'method'  => 'POST',
        'header'  => "Content-Type: application/json\r\nContent-Length: " . strlen($payload),
        'content' => $payload,
        'timeout' => 5,
    ],
]);
@file_get_contents($url, false, $context);
*/

// Beispiel 3: Datenbankabfrage
/*
$pdo = new PDO('mysql:host=localhost;dbname=calls', 'user', 'pass');
$stmt = $pdo->prepare('INSERT INTO incoming_calls (number, called_at) VALUES (?, NOW())');
$stmt->execute([$callerNumber]);
*/

exit(0);
