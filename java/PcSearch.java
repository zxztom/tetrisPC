import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import common.ResultHelper;
import common.datastore.Operations;
import common.datastore.action.Action;
import common.parser.OperationInterpreter;
import core.action.candidate.Candidate;
import core.action.candidate.CandidateFacade;
import core.action.candidate.HarddropCandidate;
import core.field.Field;
import core.field.FieldFactory;
import core.mino.MinoFactory;
import core.mino.MinoShifter;
import core.mino.Piece;
import entry.common.kicks.factory.SRSMinoRotationFactory;
import entry.common.kicks.factory.FileMinoRotationFactory;
import searcher.checker.Checker;
import searcher.checker.CheckerUsingHold;
import searcher.checker.CheckerNoHold;
import searcher.common.validator.PerfectValidator;

/** First-solution search using the pinned sfinder 1.43 public API.
 * Unlike the path CLI this does not enumerate millions of layouts.
 * Every returned route is independently reconstructed in Python.
 */
public class PcSearch {
    public static void main(String[] args) throws Exception {
        if(args.length==4 && (args[0].equals("--ground-landings") || args[0].equals("--ground180-landings") || args[0].equals("--ground180-fine-landings"))) {
            List<String> rows=Files.readAllLines(Path.of(args[1]));
            int h=Integer.parseInt(rows.get(0));
            Field f=FieldFactory.createField(rows.stream().skip(1).collect(Collectors.joining()));
            Candidate<Action> c=new GroundCandidate(new MinoFactory(),Path.of(args[3]),args[0].startsWith("--ground180"),args[0].equals("--ground180-fine-landings"));
            for(Action a:c.search(f,Piece.valueOf(args[2]),h)) System.out.println(a.getX()+","+a.getY()+","+a.getRotate().getNumber());
            return;
        }
        if (args.length==1 && args[0].equals("--worker")) {
            BufferedReader input=new BufferedReader(new InputStreamReader(System.in,StandardCharsets.UTF_8));
            String line;
            while ((line=input.readLine())!=null) {
                try { search(line.split("\t",-1)); }
                catch (GroundCandidate.BudgetExceeded budget) { System.out.println("SEARCH_BUDGET"); }
                catch (Exception error) { System.out.println("SEARCH_ERROR "+error.getClass().getSimpleName()); }
                System.out.println("END");System.out.flush();
            }
        } else search(args);
    }
    private static void search(String[] args) throws Exception {
        long deadline=args.length>6?System.nanoTime()+(long)(Double.parseDouble(args[6])*1_000_000):Long.MAX_VALUE;
        int height = Integer.parseInt(args[2]);
        String marks;
        if(args[0].startsWith("inline:")) {
            marks=args[0].substring(7);
            if(height<1 || height>6 || marks.length()!=height*10 || !marks.matches("[_IJLOSTZX]+"))
                throw new IllegalArgumentException("Invalid inline field");
        } else {
            List<String> rows = Files.readAllLines(Path.of(args[0]));
            marks=rows.stream().skip(1).collect(Collectors.joining());
        }
        Field field = FieldFactory.createField(marks);
        int depth = (height * 10 - field.getNumOfAllBlocks()) / 4;
        List<Piece> queue = args[1].chars().mapToObj(c -> Piece.valueOf(""+(char)c)).collect(Collectors.toList());
        MinoFactory factory = new MinoFactory();
        MinoShifter shifter = new MinoShifter();
        Candidate<Action> candidate = args[3].startsWith("ground")
            ? new GroundCandidate(factory,Path.of(args[5]),args[3].contains("180"),args[3].endsWith("fine"))
            : args[3].equals("hard")
            ? new HarddropCandidate(factory, shifter)
            : CandidateFacade.create90Locked(factory, shifter,
                args.length>5 ? FileMinoRotationFactory.load(Path.of(args[5])).create() : SRSMinoRotationFactory.createDefault(), height);
        if(candidate instanceof GroundCandidate)((GroundCandidate)candidate).setDeadline(deadline);
        Checker<Action> checker = args[4].equals("use")
            ? new CheckerUsingHold<Action>(factory, new PerfectValidator())
            : new CheckerNoHold<Action>(factory, new PerfectValidator());
        if(candidate instanceof GroundCandidate && !args[3].endsWith("fine") && !args[3].endsWith("plain") && depth<=6) {
            GroundCandidate shortRoutes=new GroundCandidate(factory,Path.of(args[5]),args[3].equals("ground180"),true);
            long now=System.nanoTime();
            shortRoutes.setDeadline(now+Math.min(10_000_000L,(deadline-now)/100*20));
            boolean found=false;
            try {found=checker.check(field,queue,shortRoutes,height,depth);}
            catch(GroundCandidate.BudgetExceeded budget) {/* Geometry fallback shares the original total deadline. */}
            if(found) {
                System.out.println("FINESSE_SEARCH standard_budget");
                System.out.println("SOLUTION "+OperationInterpreter.parseToString(new Operations(ResultHelper.createOperationStream(checker.getResult()))));
                return;
            }
            checker=args[4].equals("use")?new CheckerUsingHold<Action>(factory,new PerfectValidator()):new CheckerNoHold<Action>(factory,new PerfectValidator());
        }
        if (checker.check(field, queue, candidate, height, depth)) {
            if(args[3].endsWith("fine"))System.out.println("FINESSE_SEARCH standard_budget");
            System.out.println("SOLUTION " + OperationInterpreter.parseToString(new Operations(ResultHelper.createOperationStream(checker.getResult()))));
        } else {
            System.out.println("NO_SOLUTION");
        }
    }
}
