import React from "react";
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

const cards = [
  { label: "Channel analytics", detail: "Performance overview and recent videos", icon: "◫" },
  { label: "Trend radar", detail: "Discover topics gaining momentum", icon: "↗" },
  { label: "Content calendar", detail: "Plan and approve your next uploads", icon: "▦" },
  { label: "Publishing queue", detail: "Review scheduled content and status", icon: "▷" }
];

export default function App() {
  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.header}>
          <Text style={styles.eyebrow}>CREATOR INTELLIGENCE</Text>
          <Text style={styles.title}>Your creator{ "\n" }workspace.</Text>
          <Text style={styles.subtitle}>Insights, ideas and publishing—connected in one place.</Text>
        </View>
        <View style={styles.statusCard}>
          <Text style={styles.statusLabel}>MOBILE FOUNDATION</Text>
          <Text style={styles.statusTitle}>App shell is ready</Text>
          <Text style={styles.statusText}>Connect your workspace API in the next integration phase.</Text>
        </View>
        <Text style={styles.sectionTitle}>Workspace</Text>
        {cards.map((card) => (
          <View key={card.label} style={styles.card}>
            <View style={styles.icon}><Text style={styles.iconText}>{card.icon}</Text></View>
            <View style={styles.cardCopy}>
              <Text style={styles.cardTitle}>{card.label}</Text>
              <Text style={styles.cardDetail}>{card.detail}</Text>
            </View>
          </View>
        ))}
        <Text style={styles.footer}>CREATOR INTELLIGENCE · MOBILE PREVIEW</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0b0d12" },
  container: { padding: 22, paddingTop: 42, paddingBottom: 36 },
  header: { marginBottom: 28 },
  eyebrow: { color: "#8f9bb4", fontSize: 11, letterSpacing: 2.2, fontWeight: "700" },
  title: { color: "#f6f7fb", fontSize: 38, lineHeight: 42, fontWeight: "800", marginTop: 12 },
  subtitle: { color: "#9da6b8", fontSize: 15, lineHeight: 22, marginTop: 12, maxWidth: 330 },
  statusCard: { backgroundColor: "#1a2230", borderColor: "#2b3b55", borderWidth: 1, borderRadius: 20, padding: 18, marginBottom: 26 },
  statusLabel: { color: "#9cb5e6", fontSize: 10, fontWeight: "800", letterSpacing: 1.7 },
  statusTitle: { color: "#fff", fontSize: 20, fontWeight: "700", marginTop: 8 },
  statusText: { color: "#aab5c8", fontSize: 13, lineHeight: 19, marginTop: 8 },
  sectionTitle: { color: "#e8ebf4", fontSize: 18, fontWeight: "700", marginBottom: 12 },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: "#151922", borderColor: "#252c38", borderWidth: 1, borderRadius: 16, padding: 14, marginBottom: 10 },
  icon: { width: 44, height: 44, borderRadius: 12, backgroundColor: "#232d3d", alignItems: "center", justifyContent: "center" },
  iconText: { color: "#b4c8f4", fontSize: 22, fontWeight: "700" },
  cardCopy: { flex: 1, marginLeft: 14 },
  cardTitle: { color: "#f0f2f7", fontSize: 15, fontWeight: "700" },
  cardDetail: { color: "#8995a9", fontSize: 12, lineHeight: 18, marginTop: 4 },
  footer: { textAlign: "center", color: "#566174", fontSize: 10, letterSpacing: 1.2, marginTop: 28 }
});