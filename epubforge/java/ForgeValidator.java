// One JVM, many books.
//
// Measured on eight real books, 0.8 MB to 23 MB, one JVM per book:
//
//     bare JVM start (tuned)           37 ms
//     JVM + EPUBCheck classes loaded  125 ms
//     a 1.8 KB book, end to end      3602 ms
//     eight real books, in sequence  35300 ms   (4415 ms/book)
//
// A 1.8 KB book costing three and a half seconds is the whole finding: the
// cost is not the JVM and it is not the book. EPUBCheck compiles its RelaxNG
// and Schematron schemas when it starts, that takes about three and a half
// seconds, and starting a new process per book pays for it again every time.
//
// The same eight books through this driver, in one JVM:
//
//     first book                     4030 ms
//     each one after                  200-1700 ms
//     eight books, in sequence       7500 ms    (940 ms/book)
//
// So the answer to "can it be sped up" is yes, 4.7x on a batch, and the way is
// not a JVM flag — the flags were already tuned and buy tenths. It is not
// throwing the JVM away between books.
//
// What this deliberately does *not* do is reimplement any part of EPUBCheck's
// reporting. It calls `EpubChecker.run` with the identical argv the command
// line would have used, so the JSON on disk is written by EPUBCheck's own code
// and the fast answer is the same answer. `tests/test_validator_daemon.py`
// holds that to the corpus rather than to this comment.
//
// Protocol, on stdin, because a book's path may contain anything a filesystem
// allows and a line-oriented protocol would have to forbid some of it:
//
//     <decimal byte count>\n<that many bytes: argv, NUL-separated>
//
// and one line back per request: EPUBCheck's exit code, or `-1` if it threw.
// `bye`, or end of input, ends the process.

import com.adobe.epubcheck.tool.EpubChecker;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ForgeValidator {

    public static void main(String[] arguments) throws IOException {
        // The protocol writes to the real stdout, held here before anything
        // else can take it. EPUBCheck prints to `System.out` on some paths even
        // under `--quiet`, and one stray line in the middle of the answers
        // would be a desynchronised pipe rather than an error anybody could
        // read. So `System.out` is pointed at stderr for the rest of the run,
        // where the caller drains it and nothing depends on it.
        PrintStream answers =
                new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8");
        System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.err), true, "UTF-8"));

        InputStream requests = new BufferedInputStream(System.in);

        // Sent once the classes are loaded, so the caller waits for the JVM to
        // be ready instead of guessing a number of milliseconds.
        answers.println("ready");

        while (true) {
            String header = readLine(requests);
            if (header == null || header.equals("bye")) {
                return;
            }
            int length;
            try {
                length = Integer.parseInt(header.trim());
            } catch (NumberFormatException malformed) {
                return;
            }
            byte[] payload = new byte[length];
            int read = 0;
            while (read < length) {
                int chunk = requests.read(payload, read, length - read);
                if (chunk < 0) {
                    return;
                }
                read += chunk;
            }
            String[] argv = new String(payload, StandardCharsets.UTF_8).split("\0", -1);

            int code;
            try {
                // A new checker per book. Sharing one across books would share
                // whatever it accumulates, and what is worth keeping between
                // books — the compiled schemas — is static and stays anyway.
                code = new EpubChecker().run(argv);
            } catch (Throwable failure) {
                // Including Error: an OutOfMemoryError on one book must not
                // take the other books in the batch with it. The caller sees
                // -1, falls back to a fresh process for that book, and gets a
                // real answer rather than a dead pipe.
                code = -1;
            }
            answers.println(code);
        }
    }

    private static String readLine(InputStream stream) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        while (true) {
            int byteRead = stream.read();
            if (byteRead < 0) {
                return line.size() == 0 ? null : line.toString("UTF-8");
            }
            if (byteRead == '\n') {
                return line.toString("UTF-8").trim();
            }
            line.write(byteRead);
        }
    }
}
