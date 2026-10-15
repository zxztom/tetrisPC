public class InspectApi {
  public static void main(String[] args) throws Exception {
    for (String name:args) {
      Class<?> type=Class.forName(name);
      System.out.println(name);
      for (java.lang.reflect.Constructor<?> c:type.getConstructors()) System.out.println(c);
      for (java.lang.reflect.Method m:type.getDeclaredMethods()) System.out.println(m);
    }
  }
}
