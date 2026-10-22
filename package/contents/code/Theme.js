.pragma library
.import "Appearance.js" as Appearance

// Internal experimental consumer. All input remains data; no file or code loading.
var maxBytes = 65536;
var rootFields = ["formatVersion", "id", "name", "author", "license", "version", "tokens"];
var tokenFields = ["foreground", "muted", "accent", "surface", "border", "radius", "spacing", "opacity", "iconSize", "reducedMotion"];
function failure(field, code, message) {
    return {error: field + ": " + message, errors: [{field: field, code: code, message: message}]};
}
function objectError(value, field, keys) {
    if (value === null || typeof value !== "object" || Array.isArray(value))
        return failure(field, "type", "Use um objeto JSON.");
    if (Object.keys(value).some(key => keys.indexOf(key) === -1))
        return failure(field, "unknown_key", "Remova os campos desconhecidos.");
    for (const key of keys) {
        if (!Object.prototype.hasOwnProperty.call(value, key))
            return failure(field + "/" + key, "required", "Este campo é obrigatório.");
    }
    return null;
}
function validate(value) {
    const envelopeError = objectError(value, "$", rootFields);
    if (envelopeError) return envelopeError;
    if (value.formatVersion !== Appearance.formatVersion)
        return failure("$/formatVersion", "format_version", "Use o formato 0.1-experimental.");
    const result = {formatVersion: Appearance.formatVersion};
    const plain = /^[A-Za-z0-9À-ÖØ-öø-ÿ.,_+\-](?:[A-Za-z0-9À-ÖØ-öø-ÿ.,_+\- ]*[A-Za-z0-9À-ÖØ-öø-ÿ.,_+\-])?(?![\s\S])/;
    const entries = [
        ["id", /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+(?![\s\S])/, 120],
        ["name", plain, 120], ["author", plain, 120], ["license", plain, 80],
        ["version", /^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?![\s\S])/, 32]
    ];
    for (const entry of entries) {
        const key = entry[0], text = value[key], field = "$/" + key;
        if (typeof text !== "string") return failure(field, "type", "Use texto simples.");
        if (text.length < 1 || text.length > entry[2]) return failure(field, "length", "O texto excede o limite deste campo.");
        if (!entry[1].test(text)) return failure(field, "format", "Use o formato de texto simples documentado.");
        result[key] = text;
    }
    const tokens = Appearance.validateTokens(value.tokens);
    if (!tokens.value) return tokens;
    result.tokens = tokens.value;
    return {value: result, error: "", errors: []};
}
function parse(text) {
    return parseDocument(text, validate, rootFields.concat(tokenFields));
}
function parseDocument(text, validator, knownFields) {
    if (typeof text !== "string") return failure("$", "type", "Cole um documento JSON.");
    if (text.length > maxBytes) return failure("$", "size", "Use até 65536 bytes UTF-8 equivalentes.");
    let bytes = 0;
    for (let index = 0; index < text.length; index++) {
        const unit = text.charCodeAt(index);
        if (unit >= 0xd800 && unit <= 0xdbff) {
            const low = text.charCodeAt(++index);
            if (!(low >= 0xdc00 && low <= 0xdfff)) return failure("$", "utf8", "Use texto Unicode válido.");
            bytes += 4;
        } else if (unit >= 0xdc00 && unit <= 0xdfff) return failure("$", "utf8", "Use texto Unicode válido.");
        else bytes += unit < 0x80 ? 1 : unit < 0x800 ? 2 : 3;
        if (bytes > maxBytes) return failure("$", "size", "Use até 65536 bytes UTF-8 equivalentes.");
    }
    let cursor = 0;
    const finiteZeros = [];
    let problem = null;
    function reject(field, code, message) { if (!problem) problem = failure(field, code, message); return false; }
    function syntax() { return reject("$", "json", "Use um único documento JSON válido, sem BOM."); }
    function whitespace() { while (cursor < text.length && /[ \t\r\n]/.test(text.charAt(cursor))) cursor++; }
    function string() {
        const start = cursor++;
        while (cursor < text.length) {
            const character = text.charAt(cursor++);
            if (character === '"') return text.slice(start, cursor);
            if (character.charCodeAt(0) < 32) { syntax(); return null; }
            if (character === "\\") {
                const escaped = text.charAt(cursor++);
                if (escaped === "u") {
                    if (!/^[0-9a-fA-F]{4}(?![\s\S])/.test(text.slice(cursor, cursor + 4))) { syntax(); return null; }
                    cursor += 4;
                } else if ('"\\/bfnrt'.indexOf(escaped) === -1 || !escaped) { syntax(); return null; }
            }
        }
        syntax(); return null;
    }
    function value(depth, field) {
        whitespace();
        const character = text.charAt(cursor);
        if (character === "{" || character === "[") {
            if (depth + 1 > 4) return reject("$", "depth", "Use até quatro níveis de objetos ou listas.");
            const object = character === "{", end = object ? "}" : "]";
            const seen = new Set();
            let index = 0;
            cursor++; whitespace();
            if (text.charAt(cursor) === end) { cursor++; return true; }
            while (cursor < text.length) {
                let childField = field + "/" + index++;
                if (object) {
                    if (text.charAt(cursor) !== '"') return syntax();
                    const raw = string();
                    if (raw === null) return false;
                    const key = JSON.parse(raw);
                    childField = knownFields.indexOf(key) === -1 ? field : field + "/" + key;
                    if (seen.has(key)) return reject(childField, "duplicate_key", "Remova as chaves duplicadas.");
                    seen.add(key);
                    whitespace();
                    if (text.charAt(cursor++) !== ":") return syntax();
                }
                if (!value(depth + 1, childField)) return false;
                whitespace();
                if (text.charAt(cursor) === end) { cursor++; return true; }
                if (text.charAt(cursor++) !== ",") return syntax();
                whitespace();
            }
            return syntax();
        }
        if (character === '"') return string() !== null;
        for (const literal of ["true", "false", "null"]) {
            if (text.slice(cursor, cursor + literal.length) === literal) { cursor += literal.length; return true; }
        }
        for (const literal of ["NaN", "Infinity", "-Infinity"]) {
            if (text.slice(cursor, cursor + literal.length) === literal)
                return reject("$", "nonfinite", "Use números JSON finitos.");
        }
        const start = cursor;
        function digit() { const unit = text.charCodeAt(cursor); return unit >= 48 && unit <= 57; }
        if (text.charAt(cursor) === "-") cursor++;
        if (text.charAt(cursor) === "0") cursor++;
        else {
            if (!digit() || text.charAt(cursor) === "0") return syntax();
            while (digit()) cursor++;
        }
        if (text.charAt(cursor) === ".") {
            cursor++;
            if (!digit()) return syntax();
            while (digit()) cursor++;
        }
        if (text.charAt(cursor) === "e" || text.charAt(cursor) === "E") {
            cursor++;
            if (text.charAt(cursor) === "+" || text.charAt(cursor) === "-") cursor++;
            if (!digit()) return syntax();
            while (digit()) cursor++;
        }
        const lexeme = text.slice(start, cursor);
        const number = Number(lexeme);
        if (!isFinite(number)) return reject("$", "nonfinite", "Use números JSON finitos.");
        // Qt JSON.parse rejects finite decimal underflow although Number returns
        // zero. Record only verified numeric spans; never rewrite strings/keys.
        if (number === 0 && /[1-9]/.test(lexeme)) finiteZeros.push([start, cursor]);
        return true;
    }
    try {
        if (!value(0, "$")) return problem;
        whitespace();
        if (cursor !== text.length) { syntax(); return problem; }
        let document = text;
        if (finiteZeros.length) {
            const parts = [];
            let previous = 0;
            for (const span of finiteZeros) {
                parts.push(text.slice(previous, span[0]), "0");
                previous = span[1];
            }
            parts.push(text.slice(previous));
            document = parts.join("");
        }
        return validator(JSON.parse(document));
    } catch (_) { return failure("$", "json", "Use um único documento JSON válido, sem BOM."); }
}
