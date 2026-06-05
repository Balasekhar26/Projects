const crypto = require("crypto");

function computeSessionHash(records) {
  const concatenated = records.map((record) => record.integrityHash).join("|");

  return crypto.createHash("sha256").update(concatenated).digest("hex");
}

module.exports = {
  computeSessionHash,
};
