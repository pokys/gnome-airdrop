// Formatting only: all protocol details stay in the receiver.
export function bytes(value) {
    if (!Number.isFinite(value) || value < 0) return '0 B';
    if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(0)} kB`;
    return `${Math.round(value)} B`;
}

export function errorMessage(code) {
    return ({
        timeout: 'Přenos se zastavil. Zkuste soubor odeslat znovu.',
        interrupted: 'Přenos byl přerušen. Zkuste odeslání znovu.',
        invalid_archive: 'Soubor nebyl přijat celý nebo má neplatný formát. Zkuste odeslání znovu.',
        storage: 'Soubor nelze uložit. Zkontrolujte cílovou složku a volné místo.',
        limit: 'Přenos překročil limit nebo není dost volného místa.',
        unsupported_type: 'Tento typ přenosu není podporovaný.',
        busy: 'Probíhá jiný přenos. Zkuste to za chvíli.',
    })[code] ?? 'Přenos nebyl dokončen. Zkuste odeslání znovu.';
}

export function transferText(transfer) {
    if (!transfer || transfer.phase === 'idle') return ['', ''];
    const name = typeof transfer.filename === 'string' ? transfer.filename : '';
    const title = transfer.file_count > 1 ? `${transfer.file_count} souborů · ${name}` : name;
    let detail;
    switch (transfer.phase) {
    case 'waiting': detail = 'Čekám na soubor…'; break;
    case 'receiving': {
        const count = bytes(transfer.wire_bytes);
        const total = transfer.total_wire_bytes;
        const percent = Number.isFinite(total) && total > 0
            ? ` · ${Math.min(100, Math.floor(100 * transfer.wire_bytes / total))} %` : '';
        detail = `Přijímám · ${count}${percent} · ${bytes(transfer.bytes_per_second)}/s`;
        break;
    }
    case 'verifying': detail = `Ověřuji a ukládám soubor… · ${bytes(transfer.wire_bytes)}`; break;
    case 'completed': detail = 'Přijato'; break;
    case 'error': detail = errorMessage(transfer.error); break;
    default: return ['', ''];
    }
    return [title || 'Přenos souborů', detail];
}

export function durationLabel(seconds) {
    return ({0: 'Do vypnutí', 300: '5 minut', 600: '10 minut'})[seconds] ?? 'Do vypnutí';
}

export function windowText(session, now = Date.now() / 1000) {
    if (!session || !Number.isFinite(session.ends_at)) return '';
    const remaining = Math.max(0, Math.ceil(session.ends_at - now));
    if (!remaining) return 'Čas vypršel · čekám na dokončení přenosu';
    return `Zbývá ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}`;
}
