import hashlib

def getMac256Hash(challenge, appId, key):
    def padRight(original, totalWidth, ch):
        def stringFromChar(ch, count):
            s = ch
            for i in range(1, count):
                s += ch
            return s
        if len(original) < totalWidth:
            ch = ch or " "
            return original + stringFromChar(ch, totalWidth - len(original))
        else:
            return original.valueOf()
    def int32ToHexString(n):
        hexChars = "0123456789abcdef"
        hexString = ""
        for i in range(4):
            hexString += hexChars[(n >> (i * 8 + 4)) & 15]
            hexString += hexChars[(n >> (i * 8)) & 15]
        return hexString
    def int64Xor(a, b):
        sA = "{0:b}".format(a)
        sB = "{0:b}".format(b)
        sC = ""
        sD = ""
        diff = abs(len(sA) - len(sB))
        for i in range(diff):
            sD += "0"
        if len(sA) < len(sB):
            sD += sA
            sA = sD
        elif len(sB) < len(sA):
            sD += sB
            sB = sD
        for i in range(len(sA)):
            sC += "0" if sA[i] == sB[i] else "1"
        return int(sC, 2)
    def cS64_C(pdwData, pInHash, pOutHash):
        MODULUS = 2147483647
        if len(pdwData) < 2 or len(pdwData) & 1 == 1:
            return False
        ulCS64_a = pInHash[0] & MODULUS
        ulCS64_b = pInHash[1] & MODULUS
        ulCS64_c = pInHash[2] & MODULUS
        ulCS64_d = pInHash[3] & MODULUS
        ulCS64_e = 242854337
        CS64_a = ulCS64_a
        CS64_b = ulCS64_b
        CS64_c = ulCS64_c
        CS64_d = ulCS64_d
        CS64_e = ulCS64_e
        pos = 0
        mod = MODULUS
        qwDatum = 0
        qwMAC = 0
        qwSum = 0
        for i in range(len(pdwData) / 2):
            qwDatum = int(pdwData[pos])
            pos += 1
            qwDatum *= CS64_e
            qwDatum = qwDatum % mod
            qwMAC += qwDatum
            qwMAC *= CS64_a
            qwMAC += CS64_b
            qwMAC = qwMAC % mod
            qwSum += qwMAC
            qwMAC += int(pdwData[pos])
            pos += 1
            qwMAC *= CS64_c
            qwMAC += CS64_d
            qwMAC = qwMAC % mod
            qwSum += qwMAC
        qwMAC += CS64_b
        qwMAC = qwMAC % mod
        qwSum += CS64_d
        qwSum = qwSum % mod
        pOutHash[0] = qwMAC
        pOutHash[1] = qwSum
        return True
    clearText = challenge + appId
    remaining = 8 - len(clearText) % 8
    if remaining != 8:
        clearText = padRight(clearText, len(clearText) + remaining, "0")
    cchClearText = len(clearText) / 4
    pClearText = []
    pos = 0
    for i in range(cchClearText):
        pClearText = pClearText[:i] + [0] + pClearText[i:]
        pClearText[i] += ord(clearText[pos]) * 1
        pos += 1
        pClearText[i] += ord(clearText[pos]) * 256
        pos += 1
        pClearText[i] += ord(clearText[pos]) * 65536
        pos += 1
        pClearText[i] += ord(clearText[pos]) * 16777216
        pos += 1
    sha256Hash = [0, 0, 0, 0]
    hash = hashlib.sha256(challenge + key).hexdigest().upper()
    pos = 0
    for i in range(len(sha256Hash)):
        sha256Hash[i] = 0
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 1
        pos += 2
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 256
        pos += 2
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 65536
        pos += 2
        sha256Hash[i] += int(hash[pos:pos+2], 16) * 16777216
        pos += 2
    macHash = [0, 0]
    cS64_C(pClearText, sha256Hash, macHash)
    a = int64Xor(sha256Hash[0], macHash[0])
    b = int64Xor(sha256Hash[1], macHash[1])
    c = int64Xor(sha256Hash[2], macHash[0])
    d = int64Xor(sha256Hash[3], macHash[1])
    return int32ToHexString(a) + int32ToHexString(b) + int32ToHexString(c) + int32ToHexString(d)