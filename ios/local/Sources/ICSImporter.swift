import EventKit
import Foundation

/// Imports the timetable's .ics export straight into the user's calendar.
///
/// On iOS a downloaded .ics only reaches Calendar through the share sheet, so
/// instead of downloading we parse the file here and write the events with
/// EventKit. Events carry the exported UID in their notes, which lets a repeat
/// import skip what is already there.
enum ICSImporter {
    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    static func importFile(at url: URL, completion: @escaping (Result<Int, Error>) -> Void) {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else {
            completion(.failure(Failure(message: "无法读取日历文件。")))
            return
        }
        importText(text, completion: completion)
    }

    static func importText(_ text: String, completion: @escaping (Result<Int, Error>) -> Void) {
        let events = parse(text)
        guard !events.isEmpty else {
            let head = text.prefix(200).replacingOccurrences(of: "\n", with: " ")
            completion(.failure(Failure(message: "日历文件里没有可导入的日程。\n内容开头：\(head)")))
            return
        }

        let store = EKEventStore()
        let finish: (Bool, Error?) -> Void = { granted, error in
            guard granted, error == nil else {
                completion(.failure(Failure(message: "没有日历写入权限，请在 设置 → 隐私与安全性 → 日历 中允许。")))
                return
            }
            var inserted = 0
            for event in events {
                let marker = "campusMate:" + event.uid
                if existing(store: store, marker: marker, start: event.start) != nil { continue }
                let item = EKEvent(eventStore: store)
                item.title = event.title
                item.startDate = event.start
                item.endDate = event.end
                if event.allDay { item.isAllDay = true }
                item.location = event.location
                item.notes = [marker, event.details].filter { !$0.isEmpty }.joined(separator: "\n")
                item.calendar = store.defaultCalendarForNewEvents
                do {
                    try store.save(item, span: .thisEvent, commit: false)
                    inserted += 1
                } catch {
                    continue
                }
            }
            do {
                try store.commit()
                completion(.success(inserted))
            } catch {
                completion(.failure(Failure(message: "写入日历失败：\(error.localizedDescription)")))
            }
        }

        if #available(iOS 17.0, *) {
            store.requestFullAccessToEvents(completion: finish)
        } else {
            store.requestAccess(to: .event, completion: finish)
        }
    }

    private static func existing(store: EKEventStore, marker: String, start: Date) -> EKEvent? {
        let calendar = Calendar.current
        guard let dayStart = calendar.date(byAdding: .day, value: -1, to: calendar.startOfDay(for: start)),
              let dayEnd = calendar.date(byAdding: .day, value: 2, to: calendar.startOfDay(for: start)) else { return nil }
        let predicate = store.predicateForEvents(withStart: dayStart, end: dayEnd, calendars: nil)
        return store.events(matching: predicate).first { $0.notes?.contains(marker) == true }
    }

    // MARK: - Minimal iCalendar reader

    private struct Event {
        let uid: String
        let title: String
        let start: Date
        let end: Date
        let allDay: Bool
        let location: String?
        let details: String
    }

    private static func parse(_ text: String) -> [Event] {
        // RFC 5545 folds long lines with CRLF + single space.
        let unfolded = text
            .replacingOccurrences(of: "\r\n ", with: "")
            .replacingOccurrences(of: "\n ", with: "")
        var events: [Event] = []
        for block in unfolded.components(separatedBy: "BEGIN:VEVENT").dropFirst() {
            let body = block.components(separatedBy: "END:VEVENT").first ?? block
            var fields: [String: (value: String, params: [String: String])] = [:]
            for line in body.components(separatedBy: "\r\n") + body.components(separatedBy: "\n") {
                guard let colon = line.firstIndex(of: ":") else { continue }
                let head = String(line[line.startIndex..<colon])
                let value = String(line[line.index(after: colon)...])
                let parts = head.components(separatedBy: ";")
                var params: [String: String] = [:]
                for part in parts.dropFirst() {
                    let pair = part.components(separatedBy: "=")
                    if pair.count == 2 { params[pair[0].uppercased()] = pair[1] }
                }
                fields[parts[0].uppercased()] = (value, params)
            }
            guard let startField = fields["DTSTART"] else { continue }
            let allDay = startField.params["VALUE"] == "DATE"
            guard let start = date(startField.value, allDay: allDay) else { continue }
            let end = fields["DTEND"].flatMap { date($0.value, allDay: allDay) }
                ?? start.addingTimeInterval(allDay ? 86_400 : 3_600)
            events.append(Event(
                uid: fields["UID"]?.value ?? UUID().uuidString,
                title: unescape(fields["SUMMARY"]?.value ?? "课程"),
                start: start,
                end: max(end, start.addingTimeInterval(60)),
                allDay: allDay,
                location: fields["LOCATION"].map { unescape($0.value) },
                details: fields["DESCRIPTION"].map { unescape($0.value) } ?? ""
            ))
        }
        return events
    }

    private static func date(_ value: String, allDay: Bool) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = allDay ? "yyyyMMdd" : "yyyyMMdd'T'HHmmss'Z'"
        if let date = formatter.date(from: value) { return date }
        formatter.dateFormat = "yyyyMMdd'T'HHmmss"
        return formatter.date(from: value)
    }

    private static func unescape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\n", with: "\n")
            .replacingOccurrences(of: "\\,", with: ",")
            .replacingOccurrences(of: "\\;", with: ";")
            .replacingOccurrences(of: "\\\\", with: "\\")
    }
}
